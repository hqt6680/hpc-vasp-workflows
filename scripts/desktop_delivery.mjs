import net from 'node:net';
import { randomUUID } from 'node:crypto';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const PIPE_PATH = '\\\\.\\pipe\\codex-ipc';
const MAX_INPUT_BYTES = 32768;
const MAX_FRAME_BYTES = 1024 * 1024;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const STEER = 'thread-follower-steer-turn';
const START = 'thread-follower-start-turn';
const isUuid = value => typeof value === 'string' && UUID.test(value);
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const undelivered = new Set(['no-client-found', 'no-handler-for-request', 'request-version-mismatch']);

function validInput(input) {
  return object(input) && isUuid(input.threadId) && isUuid(input.clientUserMessageId) &&
    typeof input.prompt === 'string' && input.prompt.trim().length > 0 &&
    Buffer.byteLength(input.prompt, 'utf8') <= MAX_INPUT_BYTES;
}

export function encodeFrame(message) {
  const body = Buffer.from(JSON.stringify(message), 'utf8');
  if (!body.length || body.length > MAX_FRAME_BYTES) throw new Error('Invalid IPC frame size');
  const frame = Buffer.alloc(4 + body.length);
  frame.writeUInt32LE(body.length, 0);
  body.copy(frame, 4);
  return frame;
}

export function deliverNative(input, {
  connect = path => net.createConnection(path),
  timeoutMs = 15000,
} = {}) {
  if (!validInput(input)) return Promise.resolve({ status: 'unavailable' });
  const { threadId, clientUserMessageId, prompt } = input;
  const conversation = { conversationId: threadId };
  const items = [{ type: 'text', text: prompt, text_elements: [] }];
  const restoreMessage = {
    id: clientUserMessageId, text: prompt, createdAt: Date.now(),
    context: { prompt, addedFiles: [], fileAttachments: [], ideContext: null,
      imageAttachments: [], workspaceRoots: [] },
  };

  return new Promise(resolveDelivery => {
    let socket;
    let done = false;
    let possiblyDelivered = false;
    let requestId;
    let method;
    let ownerId;
    let clientId = 'initializing-client';
    let buffered = Buffer.alloc(0);
    const timer = setTimeout(fail, timeoutMs);

    function finish(result) {
      if (done) return;
      done = true;
      clearTimeout(timer);
      socket?.destroy();
      resolveDelivery(result);
    }

    function fail() {
      finish({ status: possiblyDelivered ? 'unknown' : 'unavailable' });
    }

    function request(name, params, version, targetClientId) {
      method = name;
      requestId = randomUUID();
      const frame = encodeFrame({
        type: 'request', sourceClientId: clientId, requestId,
        method, params, version, targetClientId,
      });
      possiblyDelivered = name === STEER || name === START;
      socket.write(frame);
    }

    function handle(message) {
      if (!object(message)) throw new Error('Invalid IPC message');
      if (message.type === 'client-discovery-request' && isUuid(message.requestId)) {
        socket.write(encodeFrame({ type: 'client-discovery-response',
          requestId: message.requestId, response: { canHandle: false } }));
        return;
      }
      if (message.type !== 'response' || message.requestId !== requestId) return;
      if (message.resultType === 'error') {
        if (method === 'thread-owner-discovery' && message.error === 'no-client-found') {
          finish({ status: 'unavailable', reason: 'thread_owner_missing' });
          return;
        }
        if (method === STEER && message.error ===
            'Cannot steer conversation ' + threadId + ' because its active turn already ended') {
          possiblyDelivered = false;
          request(START, { ...conversation, turnStart: {
            request: { threadId, clientUserMessageId, input: items },
            context: { restoreMessage, attachments: [], inheritThreadSettings: true },
          } }, 2, ownerId);
          return;
        }
        if (undelivered.has(message.error)) possiblyDelivered = false;
        fail();
        return;
      }
      if (message.method !== method || message.resultType !== 'success' || !object(message.result)) {
        fail();
        return;
      }
      if (method === 'initialize' && isUuid(message.result.clientId)) {
        clientId = message.result.clientId;
        request('thread-owner-discovery', { hostId: 'local', ...conversation }, 1);
        return;
      }
      if (method === 'thread-owner-discovery' && isUuid(message.handledByClientId) &&
          message.result.supportsUntrustedAppInput === true) {
        ownerId = message.handledByClientId;
        request(STEER, { ...conversation, clientUserMessageId, input: items,
          attachments: [], restoreMessage }, 1, ownerId);
        return;
      }
      const result = message.result.result;
      const turnId = method === STEER ? result?.turnId : result?.turn?.id;
      if (message.handledByClientId === ownerId &&
          typeof turnId === 'string' && turnId.trim() && turnId.length <= 200) {
        finish({ status: method === STEER ? 'steered' : 'started', turnId });
      } else {
        fail();
      }
    }

    try {
      socket = connect(PIPE_PATH);
      socket.on('error', fail);
      socket.on('close', fail);
      socket.on('end', fail);
      socket.on('connect', () => {
        if (!done) {
          try { request('initialize', { clientType: 'vasp-pbs-watcher' }, 0); }
          catch { fail(); }
        }
      });
      socket.on('data', chunk => {
        if (done) return;
        try {
          if (buffered.length + chunk.length > MAX_FRAME_BYTES + 4) {
            throw new Error('IPC receive buffer exceeded its limit');
          }
          buffered = Buffer.concat([buffered, chunk]);
          while (!done && buffered.length >= 4) {
            const length = buffered.readUInt32LE(0);
            if (!length || length > MAX_FRAME_BYTES) throw new Error('Invalid IPC frame size');
            if (buffered.length < 4 + length) break;
            const message = JSON.parse(new TextDecoder('utf-8', { fatal: true })
              .decode(buffered.subarray(4, 4 + length)));
            buffered = buffered.subarray(4 + length);
            handle(message);
          }
        } catch { fail(); }
      });
    } catch { fail(); }
  });
}

async function main() {
  let result;
  try {
    const chunks = [];
    let length = 0;
    for await (const chunk of process.stdin) {
      length += chunk.length;
      if (length > MAX_INPUT_BYTES * 2) throw new Error('Invalid input size');
      chunks.push(chunk);
    }
    const text = new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(chunks));
    result = await deliverNative(JSON.parse(text));
  } catch {
    result = { status: 'unavailable' };
  }
  process.stdout.write(JSON.stringify(result) + '\n');
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  await main();
}
