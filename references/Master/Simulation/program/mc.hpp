#ifndef MNINP2TE6_MC_HPP
#define MNINP2TE6_MC_HPP
#include "physics.hpp"
#include <numeric>
#include <limits>

namespace spin {

// 与 Python MC 保持同一单位换算，避免用另一组 kB 数值改变接受概率。
const double mev_to_kelvin=11.58875;

struct Colours {
    std::vector<int> sites,offsets,labels;
    explicit Colours(const Lattice& lattice): labels(lattice.count,-1) {
        if ((!lattice.periodic_x || lattice.nx%4==0) && (!lattice.periodic_y || lattice.ny%4==0)) {
            for (int i=0;i<lattice.count;++i) labels[i]=((i/lattice.ny)%4)*4+(i%lattice.ny)%4;
        } else {
            // 周期尺寸不能整除 4 时，根据实际三壳层邻接关系贪心着色。
            for (int i=0;i<lattice.count;++i) {
                bool forbidden[19]={false};
                for (int q=0;q<18;++q) {
                    const int n=lattice.neighbours[i][q];
                    if (n>=0 && labels[n]>=0) forbidden[labels[n]]=true;
                }
                int colour=0;
                while (colour<19 && forbidden[colour]) ++colour;
                if (colour==19) throw std::runtime_error("MC graph colouring failed");
                labels[i]=colour;
            }
        }
        int maximum=0;
        for (int i=0;i<lattice.count;++i) {
            maximum=std::max(maximum,labels[i]);
            for (int q=0;q<18;++q) {
                const int n=lattice.neighbours[i][q];
                if (n>=0 && labels[n]==labels[i])
                    throw std::runtime_error("interacting sites share an MC colour");
            }
        }
        offsets.push_back(0);
        for (int colour=0;colour<=maximum;++colour) {
            const std::size_t before=sites.size();
            for (int i=0;i<lattice.count;++i) if (labels[i]==colour) sites.push_back(i);
            if (sites.size()!=before) offsets.push_back(static_cast<int>(sites.size()));
        }
    }
    int count() const { return static_cast<int>(offsets.size())-1; }
};

// 仅改变一个格点时的完整能量差。有效场已包含线性项和 2K*Sz，
// 还需加 -K*(delta Sz)^2 才能精确得到二次各向异性的能量差。
inline double mc_delta(const Model& m,const State& s,int site,const Vec& proposal,double B) {
    const Vec delta=proposal-s[site];
    return -dot(delta,m.field_mev(s,site,B,0))-m.material.K*delta.z*delta.z;
}

struct MCResult {
    std::uint64_t sweeps;
    double acceptance;
};

template<class Callback>
MCResult monte_carlo(const Model& m,State& s,const Colours& colours,double T,double B,
                    double proposal_sigma,std::uint64_t equilibration,std::uint64_t measurement,
                    std::uint64_t seed,Callback callback,const State* prescribed_normal=0,
                    const std::vector<double>* prescribed_uniform=0,
                    const std::vector<int>* prescribed_order=0) {
    if (T<=0) throw std::runtime_error("MC requires positive temperature");
    const std::uint64_t total=equilibration+measurement;
    const int groups=colours.count();
    std::vector<int> order(groups),counts(omp_get_max_threads());
    std::iota(order.begin(),order.end(),0);
    std::mt19937_64 order_rng(mixed_seed(seed^UINT64_C(0x7265706c696361)));
    double accepted_measurement=0;
    std::uint64_t measured=0,completed=0;
    bool stop=false;
    #pragma omp parallel shared(order,counts,stop,completed,measured,accepted_measurement)
    {
        const int thread=omp_get_thread_num(),team=omp_get_num_threads();
        std::mt19937_64 rng(mixed_seed(seed+static_cast<std::uint64_t>(thread)));
        std::normal_distribution<double> normal(0,1);
        std::uniform_real_distribution<double> uniform(0,1);
        for (std::uint64_t sweep=0;sweep<total && !stop;++sweep) {
            int accepted=0;
            #pragma omp single
            {
                if (prescribed_order) {
                    for (int c=0;c<groups;++c) order[c]=(*prescribed_order)[sweep*groups+c];
                } else std::shuffle(order.begin(),order.end(),order_rng);
            }
            for (int position=0;position<groups;++position) {
                const int colour=order[position],first=colours.offsets[colour];
                const int size=colours.offsets[colour+1]-first,base=size/team,remainder=size%team;
                const int begin=first+thread*base+std::min(thread,remainder);
                const int end=begin+base+(thread<remainder ? 1 : 0);
                for (int p=begin;p<end;++p) {
                    const int site=colours.sites[p];
                    Vec gaussian;
                    double draw;
                    if (prescribed_normal) gaussian=(*prescribed_normal)[sweep*m.lattice.count+site];
                    else {
                        const double x=normal(rng),y=normal(rng),z=normal(rng);
                        gaussian=Vec(x,y,z);
                    }
                    if (prescribed_uniform) draw=(*prescribed_uniform)[sweep*m.lattice.count+site];
                    else draw=uniform(rng);
                    const Vec proposal=unit(s[site]+gaussian*proposal_sigma);
                    const double delta=mc_delta(m,s,site,proposal,B)*mev_to_kelvin;
                    if (delta<=0 || draw<std::exp(-delta/T)) { s[site]=proposal; ++accepted; }
                }
                // 同色格点之间无相互作用；下一颜色读取之前需要同步。
                #pragma omp barrier
            }
            counts[thread]=accepted;
            #pragma omp barrier
            #pragma omp single
            {
                completed=sweep+1;
                if (sweep>=equilibration) {
                    int count=0;
                    for (int t=0;t<team;++t) count+=counts[t];
                    accepted_measurement+=static_cast<double>(count)/m.lattice.count; ++measured;
                }
                if (completed%32==0 || completed==total)
                    stop=callback(completed,s);
            }
        }
    }
    return MCResult{completed,measured ? accepted_measurement/measured : std::numeric_limits<double>::quiet_NaN()};
}
} // namespace spin
#endif
