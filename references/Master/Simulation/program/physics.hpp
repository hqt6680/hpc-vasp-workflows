#ifndef MNINP2TE6_PHYSICS_HPP
#define MNINP2TE6_PHYSICS_HPP

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <functional>
#include <limits>
#include <random>
#include <stdexcept>
#include <vector>
#include <omp.h>

namespace spin {

// 物理常数与 Python 版完全相同：能量以 meV 输入，LLG 有效场以 T 计算。
const double mu_b = 9.274e-24;
const double kb = 1.380649e-23;
const double mev_j = 1.602176634e-22;
const double gamma = 1.76e11;

struct Vec {
    double x, y, z;
    Vec(double a=0, double b=0, double c=0): x(a), y(b), z(c) {}
    Vec operator+(const Vec& b) const { return Vec(x+b.x, y+b.y, z+b.z); }
    Vec operator-(const Vec& b) const { return Vec(x-b.x, y-b.y, z-b.z); }
    Vec operator*(double a) const { return Vec(a*x, a*y, a*z); }
};
inline double dot(const Vec& a, const Vec& b) { return a.x*b.x+a.y*b.y+a.z*b.z; }
inline Vec cross(const Vec& a, const Vec& b) {
    return Vec(a.y*b.z-a.z*b.y, a.z*b.x-a.x*b.z, a.x*b.y-a.y*b.x);
}
inline Vec unit(const Vec& a) { return a*(1.0/std::max(std::sqrt(dot(a,a)),1e-30)); }
inline Vec tangent(const Vec& a, const Vec& s) { return a-s*dot(a,s); }
typedef std::vector<Vec> State;

struct Material {
    std::array<double,3> J;
    double lambda, K, D, Kxy, Kxz, moment, lattice_constant;
    bool neel;
    Material(): J{{1.71,-0.11,-0.09}}, lambda(0), K(-0.5125), D(0.63),
        Kxy(0), Kxz(0), moment(4.2), lattice_constant(1), neel(false) {}
};

// x/y 独立选择周期或开放边界；开放方向越界的三阶近邻键均记为 -1。
struct Lattice {
    int nx, ny, count;
    const bool periodic_x,periodic_y,periodic;
    std::vector<std::array<int,18> > neighbours;
    static int checked_count(int length, int width) {
        if (length<3 || width<3 || length>std::numeric_limits<int>::max()/width)
            throw std::runtime_error("Nx and Ny must be >=3 and Nx*Ny must fit in int");
        return length*width;
    }
    Lattice(int length, int width,bool wrap_x=false,bool wrap_y=false): nx(length), ny(width),
        count(checked_count(length,width)), periodic_x(wrap_x),periodic_y(wrap_y),
        periodic(wrap_x && wrap_y),neighbours(count) {
        // 奇偶行错位的晶格沿 y 首尾连接时，Ny 必须为偶数，保证键的互反性。
        if (periodic_y && ny%2) throw std::runtime_error("periodic y boundary requires even Ny");
        const int offsets[3][6][3] = {
            {{1,0,0},{0,1,1},{-1,1,1},{-1,0,0},{-1,-1,1},{0,-1,1}},
            {{1,1,1},{1,-1,1},{0,2,0},{0,-2,0},{-2,1,1},{-2,-1,1}},
            {{2,0,0},{-2,0,0},{1,2,0},{1,-2,0},{-1,2,0},{-1,-2,0}}
        };
        for (int i=0; i<nx; ++i) for (int j=0; j<ny; ++j)
            for (int shell=0; shell<3; ++shell) for (int q=0; q<6; ++q) {
                int ii=i+offsets[shell][q][0]+offsets[shell][q][2]*(j&1);
                int jj=j+offsets[shell][q][1];
                if (periodic_x) ii=(ii%nx+nx)%nx;
                if (periodic_y) jj=(jj%ny+ny)%ny;
                neighbours[i*ny+j][shell*6+q] =
                    (ii>=0 && ii<nx && jj>=0 && jj<ny) ? ii*ny+jj : -1;
            }
    }
};

struct Model {
    Material material;
    Lattice lattice;
    std::array<Vec,6> dmi;
    double tesla_per_mev;
    Model(const Material& m, int length, int width,bool wrap_x=false,bool wrap_y=false): material(m),
        lattice(length,width,wrap_x,wrap_y), tesla_per_mev(mev_j/(m.moment*mu_b)) {
        const double r=std::sqrt(3.0)/2;
        const Vec bonds[6]={Vec(1,0,0),Vec(.5,r,0),Vec(-.5,r,0),
                           Vec(-1,0,0),Vec(-.5,-r,0),Vec(.5,-r,0)};
        for (int q=0; q<6; ++q)
            dmi[q]=(m.neel ? cross(Vec(0,0,1),bonds[q]) : bonds[q])*m.D;
    }
    Vec electric_field(const Vec& s, int direction) const {
        const double a=material.Kxy, b=material.Kxz, r=std::sqrt(3.0)/2;
        if (direction==0) return Vec(a*s.y+b*s.z,a*s.x,b*s.x);
        if (direction==1)
            return Vec(a*(r*s.x-.5*s.y)-.5*b*s.z,
                       a*(-.5*s.x-r*s.y)+r*b*s.z,b*(-.5*s.x+r*s.y));
        return Vec(a*(-r*s.x-.5*s.y)-.5*b*s.z,
                   a*(-.5*s.x+r*s.y)-r*b*s.z,b*(-.5*s.x-r*s.y));
    }
    Vec field_mev(const State& s, int i, double B, double Ez) const {
        Vec h;
        const std::array<int,18>& near=lattice.neighbours[i];
        for (int q=0; q<6; ++q) {
            const int n=near[q];
            if (n>=0) {
                h=h+s[n]*material.J[0]+cross(s[n],dmi[q]);
                h.z+=material.lambda*s[n].z;
                if (Ez!=0) h=h+electric_field(s[n],q%3)*Ez;
            }
            for (int shell=1; shell<3; ++shell) {
                const int other=near[6*shell+q];
                if (other>=0) h=h+s[other]*material.J[shell];
            }
        }
        h.z+=2*material.K*s[i].z+material.moment*mu_b/mev_j*B;
        return h;
    }
    State fields(const State& s, double B, double Ez) const {
        State h(s.size());
        #pragma omp parallel for schedule(static)
        for (int i=0; i<lattice.count; ++i) h[i]=field_mev(s,i,B,Ez);
        return h;
    }
    double energy(const State& s, double B, double Ez) const {
        double sum=0;
        const double zeeman=material.moment*mu_b/mev_j*B;
        #pragma omp parallel for reduction(+:sum) schedule(static)
        for (int i=0; i<lattice.count; ++i)
            sum+=-.5*dot(s[i],field_mev(s,i,B,Ez))-.5*zeeman*s[i].z;
        return sum;
    }
    // 日志回调已在线程组内部，串行求能量可避免嵌套 OpenMP 线程组。
    double energy_serial(const State& s, double B, double Ez) const {
        double sum=0;
        const double zeeman=material.moment*mu_b/mev_j*B;
        for (int i=0; i<lattice.count; ++i)
            sum+=-.5*dot(s[i],field_mev(s,i,B,Ez))-.5*zeeman*s[i].z;
        return sum;
    }
};

inline std::uint64_t mixed_seed(std::uint64_t x) {
    x+=UINT64_C(0x9e3779b97f4a7c15);
    x=(x^(x>>30))*UINT64_C(0xbf58476d1ce4e5b9);
    x=(x^(x>>27))*UINT64_C(0x94d049bb133111eb);
    return x^(x>>31);
}
inline State random_state(int count, std::uint64_t seed) {
    std::mt19937_64 rng(seed);
    std::normal_distribution<double> normal(0,1);
    State s(count);
    for (int i=0; i<count; ++i) {
        // 显式固定抽样次序；C++11 不保证函数实参的求值顺序。
        const double x=normal(rng), y=normal(rng), z=normal(rng);
        s[i]=unit(Vec(x,y,z));
    }
    return s;
}
inline Vec rhs(const Vec& s, const Vec& h, double alpha) {
    return (cross(s,h)+(s*dot(s,h)-h)*alpha)*(-gamma/(1+alpha*alpha));
}

// 原始 C++ 内核保留为对照，便于在同一节点比较优化前后的数值与速度。
// 预测/校正必须共享同一份热噪声，两个阶段之间必须同步。
template<class Callback>
std::uint64_t integrate_reference(const Model& model, State& state, double T, double B, double Ez,
                       double alpha, double dt, bool thermal, std::uint64_t steps,
                       std::uint64_t seed, Callback callback,
                       const State* prescribed_noise=0) {
    const int count=model.lattice.count;
    State next(count), predicted(count), ds1(count), noise(count);
    const double sigma=(thermal && T>0) ?
        std::sqrt(2*alpha*kb*T/(gamma*model.material.moment*mu_b*dt)) : 0;
    bool stop=false;
    std::uint64_t completed=0;
    #pragma omp parallel shared(stop,completed)
    {
        std::mt19937_64 rng(mixed_seed(seed+static_cast<std::uint64_t>(omp_get_thread_num())));
        std::normal_distribution<double> normal(0,1);
        for (std::uint64_t step=0; step<steps && !stop; ++step) {
            const State& current=(step%2==0) ? state : next;
            State& following=(step%2==0) ? next : state;
            #pragma omp for schedule(static)
            for (int i=0; i<count; ++i) {
                Vec thermal_field;
                if (sigma!=0) {
                    if (prescribed_noise) thermal_field=(*prescribed_noise)[step*count+i]*sigma;
                    else {
                        const double x=normal(rng), y=normal(rng), z=normal(rng);
                        thermal_field=Vec(x,y,z)*sigma;
                    }
                }
                noise[i]=thermal_field;
                const Vec h=model.field_mev(current,i,B,Ez)*model.tesla_per_mev+thermal_field;
                ds1[i]=rhs(current[i],h,alpha);
                predicted[i]=unit(current[i]+ds1[i]*dt);
            }
            #pragma omp for schedule(static)
            for (int i=0; i<count; ++i) {
                const Vec h=model.field_mev(predicted,i,B,Ez)*model.tesla_per_mev+noise[i];
                const Vec ds2=rhs(predicted[i],h,alpha);
                following[i]=unit(current[i]+(ds1[i]+ds2)*(.5*dt));
            }
            if ((step+1)%64==0 || step+1==steps) {
                #pragma omp single
                {
                    completed=step+1;
                    stop=callback(completed,following);
                }
            }
        }
    }
    if (completed%2) state.swap(next);
    return completed;
}

// 每个外场点只准备一次系数，把 meV→T 换算移出每个格点/每个时间步。
// Bloch 和 Neel DMI 均位于 xy 平面，因此 Dz 恒为零，可省去对应乘法。
struct PreparedField {
    const Model& model;
    std::array<double,3> J;
    std::array<Vec,6> D;
    double Jz,K,B,Kxy,Kxz;
    PreparedField(const Model& m,double field,double electric): model(m) {
        for (int shell=0;shell<3;++shell) J[shell]=m.material.J[shell]*m.tesla_per_mev;
        for (int q=0;q<6;++q) D[q]=m.dmi[q]*m.tesla_per_mev;
        Jz=J[0]+m.material.lambda*m.tesla_per_mev;
        K=2*m.material.K*m.tesla_per_mev; B=field;
        Kxy=electric*m.material.Kxy*m.tesla_per_mev;
        Kxz=electric*m.material.Kxz*m.tesla_per_mev;
    }
    template<bool Periodic,bool Electric>
    inline Vec at(const State& s,int site) const {
        Vec h;
        const std::array<int,18>& near=model.lattice.neighbours[site];
        for (int q=0;q<6;++q) {
            const int n=near[q];
            if (Periodic || n>=0) {
                const Vec& v=s[n];
                h.x+=J[0]*v.x-D[q].y*v.z;
                h.y+=J[0]*v.y+D[q].x*v.z;
                h.z+=Jz*v.z+D[q].y*v.x-D[q].x*v.y;
                if (Electric) {
                    const double r=std::sqrt(3.0)/2;
                    if (q%3==0) {
                        h.x+=Kxy*v.y+Kxz*v.z; h.y+=Kxy*v.x; h.z+=Kxz*v.x;
                    } else if (q%3==1) {
                        h.x+=Kxy*(r*v.x-.5*v.y)-.5*Kxz*v.z;
                        h.y+=Kxy*(-.5*v.x-r*v.y)+r*Kxz*v.z;
                        h.z+=Kxz*(-.5*v.x+r*v.y);
                    } else {
                        h.x+=Kxy*(-r*v.x-.5*v.y)-.5*Kxz*v.z;
                        h.y+=Kxy*(-.5*v.x+r*v.y)-r*Kxz*v.z;
                        h.z+=Kxz*(-.5*v.x-r*v.y);
                    }
                }
            }
            for (int shell=1;shell<3;++shell) {
                const int other=near[6*shell+q];
                if (Periodic || other>=0) h=h+s[other]*J[shell];
            }
        }
        h.z+=K*s[site].z+B;
        return h;
    }
};

template<bool Periodic,bool Electric,class Callback>
std::uint64_t integrate_optimized(const Model& model, State& state, double T, double B, double Ez,
                       double alpha, double dt, bool thermal, std::uint64_t steps,
                       std::uint64_t seed, Callback callback,const State* prescribed_noise) {
    const int count=model.lattice.count;
    const PreparedField field(model,B,Ez);
    State next(count),predicted(count),ds1(count),noise(count);
    const double sigma=(thermal && T>0) ?
        std::sqrt(2*alpha*kb*T/(gamma*model.material.moment*mu_b*dt)) : 0;
    bool stop=false;
    std::uint64_t completed=0;
    #pragma omp parallel shared(stop,completed)
    {
        const int thread=omp_get_thread_num(),team=omp_get_num_threads();
        // 等价于无 chunk 的静态调度，每线程的连续格点区间只计算一次。
        const int base=count/team,remainder=count%team;
        const int begin=thread*base+std::min(thread,remainder);
        const int end=begin+base+(thread<remainder ? 1 : 0);
        std::mt19937_64 rng(mixed_seed(seed+static_cast<std::uint64_t>(thread)));
        std::normal_distribution<double> normal(0,1);
        for (std::uint64_t step=0;step<steps && !stop;++step) {
            const State& current=(step%2==0) ? state : next;
            State& following=(step%2==0) ? next : state;
            for (int i=begin;i<end;++i) {
                Vec thermal_field;
                if (sigma!=0) {
                    if (prescribed_noise) thermal_field=(*prescribed_noise)[step*count+i]*sigma;
                    else {
                        const double x=normal(rng),y=normal(rng),z=normal(rng);
                        thermal_field=Vec(x,y,z)*sigma;
                    }
                }
                noise[i]=thermal_field;
                ds1[i]=rhs(current[i],field.at<Periodic,Electric>(current,i)+thermal_field,alpha);
                predicted[i]=unit(current[i]+ds1[i]*dt);
            }
            // 所有预测态写完后，校正阶段才可读取相邻格点的预测态。
            #pragma omp barrier
            for (int i=begin;i<end;++i) {
                const Vec ds2=rhs(predicted[i],field.at<Periodic,Electric>(predicted,i)+noise[i],alpha);
                following[i]=unit(current[i]+(ds1[i]+ds2)*(.5*dt));
            }
            // 所有校正态写完后，下一步才可开始；保留这两个必要的同步点。
            #pragma omp barrier
            if ((step+1)%64==0 || step+1==steps) {
                #pragma omp single
                { completed=step+1; stop=callback(completed,following); }
            }
        }
    }
    if (completed%2) state.swap(next);
    return completed;
}

template<class Callback>
std::uint64_t integrate(const Model& model,State& state,double T,double B,double Ez,
                       double alpha,double dt,bool thermal,std::uint64_t steps,
                       std::uint64_t seed,Callback callback,const State* prescribed_noise=0,
                       bool reference=false) {
    if (reference) return integrate_reference(model,state,T,B,Ez,alpha,dt,thermal,steps,seed,callback,prescribed_noise);
    // 在进入积分前选择专用内核，周期边界/零电场不再逐格点判断。
    const bool electric=Ez!=0 && (model.material.Kxy!=0 || model.material.Kxz!=0);
    if (model.lattice.periodic) {
        if (electric) return integrate_optimized<true,true>(model,state,T,B,Ez,alpha,dt,thermal,steps,seed,callback,prescribed_noise);
        return integrate_optimized<true,false>(model,state,T,B,Ez,alpha,dt,thermal,steps,seed,callback,prescribed_noise);
    }
    if (electric) return integrate_optimized<false,true>(model,state,T,B,Ez,alpha,dt,thermal,steps,seed,callback,prescribed_noise);
    return integrate_optimized<false,false>(model,state,T,B,Ez,alpha,dt,thermal,steps,seed,callback,prescribed_noise);
}

} // namespace spin
#endif
