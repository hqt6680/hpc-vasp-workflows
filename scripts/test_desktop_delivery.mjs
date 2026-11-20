import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import test from 'node:test';
import { deliverNative, encodeFrame } from './desktop_delivery.mjs';

const ids = {
  thread: '2a0e3430-73a8-4655-8d7a-26fdce609c7b',
  message: 'ff48237b-c44b-412e-9d28-58647640bc58',
  client: '0bdb151f-219c-45f9-a173-08e965bb3347',
  owner: 'b35e65a1-34ee-4fcd-b270-6ad02368bd34',
};
const input = {
  threadId: ids.thread, clientUserMessageId: ids.message, prompt: 'PBS 作业结束',
};
const steer = 'thread-follower-steer-turn';
const start = 'thread-follower-start-turn';

function desktop(handler) {
  const sent = [];
  const socket = new EventEmitter();
  socket.destroy = () => {};
  socket.write = frame => {
    const request = JSON.parse(frame.subarray(4));
    sent.push(request);
    const reply = (value, error) => {
      const response = encodeFrame({
        type: 'response', requestId: request.requestId, method: request.method,
        handledByClientId: ids.owner,
        ...(error ? { resultType: 'error', error } : { resultType: 'success', result: value }),
      });
      queueMicrotask(() => {
        socket.emit('data', response.subarray(0, 3));
        socket.emit('data', response.subarray(3));
      });
    };
    if (request.method === 'initialize') reply({ clientId: ids.client });
    else handler(request, reply, socket);
  };
  const connect = () => {
    queueMicrotask(() => socket.emit('connect'));
    return socket;
  };
  return { sent, connect };
}

test('steers the existing turn once', async () => {
  const fixture = desktop((request, reply) => {
    if (request.method === 'thread-owner-discovery') reply({ supportsUntrustedAppInput: true });
    else reply({ result: { turnId: 'active-turn' } });
  });
  assert.deepEqual(await deliverNative(input, fixture), { status: 'steered', turnId: 'active-turn' });
  assert.deepEqual(fixture.sent.map(row => row.method), ['initialize', 'thread-owner-discovery', steer]);
  const request = fixture.sent.at(-1);
  assert.equal(request.targetClientId, ids.owner);
  assert.equal(request.params.clientUserMessageId, ids.message);
  assert.equal(request.params.input[0].text, input.prompt);
});

test('explicit inactive-turn rejection starts a new turn without queueing', async () => {
  const fixture = desktop((request, reply) => {
    if (request.method === 'thread-owner-discovery') reply({ supportsUntrustedAppInput: true });
    else if (request.method === steer) {
      reply(null, 'Cannot steer conversation ' + ids.thread + ' because its active turn already ended');
    } else reply({ result: { turn: { id: 'new-turn' } } });
  });
  assert.deepEqual(await deliverNative(input, fixture), { status: 'started', turnId: 'new-turn' });
  assert.deepEqual(fixture.sent.map(row => row.method), ['initialize', 'thread-owner-discovery', steer, start]);
  const request = fixture.sent.at(-1);
  assert.equal(request.version, 2);
  assert.equal(request.params.turnStart.request.threadId, ids.thread);
  assert.equal(request.params.turnStart.request.clientUserMessageId, ids.message);
});

test('no owner is retryable without sending a message', async () => {
  const fixture = desktop((_, reply) => reply(null, 'no-client-found'));
  assert.deepEqual(await deliverNative(input, fixture),
    { status: 'unavailable', reason: 'thread_owner_missing' });
  assert.deepEqual(fixture.sent.map(row => row.method), ['initialize', 'thread-owner-discovery']);
});

test('disconnect after a steer cannot safely fall back to start', async () => {
  const fixture = desktop((request, reply, socket) => {
    if (request.method === 'thread-owner-discovery') reply({ supportsUntrustedAppInput: true });
    else queueMicrotask(() => socket.emit('close'));
  });
  assert.deepEqual(await deliverNative(input, fixture), { status: 'unknown' });
  assert.equal(fixture.sent.at(-1).method, steer);
});

test('timeout after a steer is ambiguous', async () => {
  const fixture = desktop((request, reply) => {
    if (request.method === 'thread-owner-discovery') reply({ supportsUntrustedAppInput: true });
  });
  assert.deepEqual(await deliverNative(input, { ...fixture, timeoutMs: 20 }), { status: 'unknown' });
  assert.equal(fixture.sent.at(-1).method, steer);
});

test('oversized IPC input stops the client without another send', async () => {
  const fixture = desktop((request, reply, socket) => {
    if (request.method === 'thread-owner-discovery') reply({ supportsUntrustedAppInput: true });
    else queueMicrotask(() => socket.emit('data', Buffer.alloc(1024 * 1024 + 5)));
  });
  assert.deepEqual(await deliverNative(input, fixture), { status: 'unknown' });
  assert.equal(fixture.sent.filter(row => row.method === steer).length, 1);
  assert.equal(fixture.sent.at(-1).method, steer);
});
