#ifndef NANORIBBON_IO_HPP
#define NANORIBBON_IO_HPP
#include "physics.hpp"
#include "npy.hpp"
#include <cerrno>
#include <cctype>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <sstream>
#include <string>
#include <sys/stat.h>
#ifdef _WIN32
#include <codecvt>
#include <locale>
#include <direct.h>
#include <process.h>
#else
#include <sys/wait.h>
#include <unistd.h>
#endif

using spin::Vec;
using spin::State;
using spin::Model;
typedef std::chrono::steady_clock Clock;
static volatile std::sig_atomic_t received_signal=0;
// 信号处理函数只设置标志；构型保存放在完成一个计算批次后的安全位置。
static void on_signal(int number) { received_signal=number; }
static double seconds(Clock::time_point start) {
    return std::chrono::duration<double>(Clock::now()-start).count();
}
static std::string trim(const std::string& s) {
    const std::size_t first=s.find_first_not_of(" \t\r\n");
    return first==std::string::npos ? "" : s.substr(first,s.find_last_not_of(" \t\r\n")-first+1);
}
static std::string join(const std::string& a, const std::string& b) {
    return a.empty() ? b : a+"/"+b;
}
static std::string parent_path(const std::string& path) {
    const std::size_t separator=path.find_last_of("/\\");
    return separator==std::string::npos ? "." : path.substr(0,separator+1);
}
static std::string expanded_path(const std::string& path) {
    if (path.size()>1 && path[0]=='~' && (path[1]=='/' || path[1]=='\\')) {
        const char* home=std::getenv("HOME");
        if (!home) home=std::getenv("USERPROFILE");
        if (home) return std::string(home)+path.substr(1);
    }
    return path;
}
static bool absolute_path(const std::string& path) {
    return !path.empty() && (path[0]=='/' || path[0]=='\\' || (path.size()>1 && path[1]==':'));
}
static bool regular_file(const std::string& path) {
    struct stat info;
    return stat(path.c_str(),&info)==0 && (info.st_mode&S_IFMT)==S_IFREG;
}
static std::string relative_to(const std::string& base,const std::string& path) {
    const std::string expanded=expanded_path(path);
    return absolute_path(expanded) ? expanded : join(base,expanded);
}
static void directories(const std::string& path) {
    if (path.empty()) throw std::runtime_error("output path cannot be empty");
    for (std::size_t i=1; i<=path.size(); ++i) {
        if (i!=path.size() && path[i]!='/' && path[i]!='\\') continue;
        const std::string part=path.substr(0,i);
        if (part.empty() || part=="." || part.back()==':') continue;
        #ifdef _WIN32
        const int code=_mkdir(part.c_str());
        #else
        const int code=mkdir(part.c_str(),0775);
        #endif
        if (code!=0 && errno!=EEXIST) throw std::runtime_error("cannot create directory: "+part);
    }
}
static void check_output(const std::ofstream& stream, const std::string& path) {
    if (!stream) throw std::runtime_error("cannot write output: "+path);
}
static void save_state(const State& s, const std::string& path) {
    std::ofstream out(path.c_str());
    out<<std::setprecision(17);
    for (std::size_t i=0; i<s.size(); ++i) out<<s[i].x<<' '<<s[i].y<<' '<<s[i].z<<'\n';
    out.close();
    check_output(out,path);
}
static void save_checkpoint(const State& s, const std::string& directory, int point,
                            std::uint64_t iteration, double T, double B, double Ez) {
    const std::string path=join(directory,"checkpoint.txt"), temporary=path+".tmp";
    std::ofstream out(temporary.c_str());
    out<<std::setprecision(17)<<"# point="<<point<<" iteration="<<iteration<<" T_K="<<T<<" B_T="<<B<<" Ez="<<Ez<<'\n';
    for (std::size_t i=0; i<s.size(); ++i) out<<s[i].x<<' '<<s[i].y<<' '<<s[i].z<<'\n';
    out.close(); check_output(out,temporary);
    // Linux 上用原子重命名替换检查点，避免强制停止时损坏上一份完整构型。
    // 条件写入 TXT 注释头，Python loadtxt 和本程序均可直接读取。
    #ifdef _WIN32
    std::remove(path.c_str());
    #endif
    if (std::rename(temporary.c_str(),path.c_str())!=0) throw std::runtime_error("cannot replace checkpoint: "+path);
    std::ofstream info(join(directory,"checkpoint.info").c_str());
    info<<std::setprecision(17)<<"point="<<point<<"\niteration="<<iteration<<"\nT_K="<<T<<"\nB_T="<<B<<"\nEz="<<Ez<<'\n';
    info.close(); check_output(info,join(directory,"checkpoint.info"));
}
static State read_vectors(const std::string& path) {
    std::ifstream in(path.c_str());
    if (!in) throw std::runtime_error("cannot read: "+path);
    State s;
    std::string line;
    while (std::getline(in,line)) {
        line=trim(line.substr(0,line.find('#')));
        if (line.empty()) continue;
        std::istringstream row(line);
        Vec value;
        std::string extra;
        if (!(row>>value.x>>value.y>>value.z) || (row>>extra) ||
            !std::isfinite(value.x) || !std::isfinite(value.y) || !std::isfinite(value.z))
            throw std::runtime_error("expected three finite columns per row in "+path);
        s.push_back(value);
    }
    if (!in.eof()) throw std::runtime_error("failed reading: "+path);
    return s;
}

static double number(const std::string& value) {
    std::size_t used=0;
    const double result=std::stod(value,&used);
    if (used!=value.size() || !std::isfinite(result))
        throw std::runtime_error("expected finite number: "+value);
    return result;
}
static int integer(const std::string& value) {
    const double n=number(value);
    if (n!=std::floor(n) || n<std::numeric_limits<int>::min() || n>std::numeric_limits<int>::max())
        throw std::runtime_error("invalid integer: "+value);
    return static_cast<int>(n);
}
static std::uint64_t unsigned_integer(const std::string& value) {
    std::size_t used=0;
    if (value.empty() || value[0]=='-') throw std::runtime_error("invalid unsigned integer: "+value);
    const std::uint64_t n=std::stoull(value,&used);
    if (used!=value.size()) throw std::runtime_error("invalid unsigned integer: "+value);
    return n;
}
static bool boolean(const std::string& s) {
    if (s=="true" || s=="1") return true;
    if (s=="false" || s=="0") return false;
    throw std::runtime_error("expected true/false: "+s);
}
static int setup_threads(int requested) {
    // PBS_NODEFILE 每个 CPU 槽位一行；禁止一个共享内存进程跨多个节点。
    int allocation=0;
    if (const char* path=std::getenv("PBS_NODEFILE")) {
        std::ifstream in(path);
        std::string host,first;
        if (!in) throw std::runtime_error("cannot read PBS_NODEFILE");
        while (in>>host) {
            if (first.empty()) first=host;
            if (host!=first) throw std::runtime_error("this program supports one CPU node per process");
            ++allocation;
        }
        if (!allocation) throw std::runtime_error("PBS_NODEFILE is empty");
    }
    const int threads=requested ? requested : (allocation ? allocation : omp_get_max_threads());
    if (allocation && threads>allocation) throw std::runtime_error("threads exceeds the allocated PBS ppn");
    omp_set_dynamic(0);
    omp_set_num_threads(threads);
    int actual=0;
    #pragma omp parallel
    {
        #pragma omp single
        actual=omp_get_num_threads();
    }
    std::cout<<"[CPU] Requested/effective OpenMP threads: "<<threads<<'/'<<actual<<'\n';
    if (actual!=threads) throw std::runtime_error("OpenMP limited the thread count; check OMP_THREAD_LIMIT");
    return actual;
}

#endif
