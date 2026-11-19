#ifndef NANORIBBON_RELAXATION_HPP
#define NANORIBBON_RELAXATION_HPP

// 仅查找同材料、Nx/Ny、x/y 边界和 T/B/Ez 对应的完整场点，不使用 final/checkpoint。
// 单温和多温目录互查，便于先退火/扫磁场，再在另一份配置中加入电场。
static std::string cached_state(const Config& c,const std::string& kind,double T,double B,double Ez) {
    if (!c.reuse_states) return "";
    std::vector<std::string> kinds(1,kind);
    if (kind.compare(0,12,"temperature_")==0) kinds.push_back(kind.substr(12));
    else if (kind!="temperature") kinds.push_back("temperature_"+kind);
    const std::string label=snapshot_label(T,B,Ez);
    // 优先查全部新尺寸目录，再兼容上一版扁平目录；旧文件只读，不移动或覆盖。
    for (int layout=0;layout<2;++layout) for (const std::string& candidate:kinds) {
        const std::string stem=layout==0 ? join(relaxation_directory(c,candidate),label)
            : join(join(engine_directory(c),candidate),geometry_name(c)+"_"+candidate+"_relaxation_"+label);
        for (const std::string& extension:{std::string(".txt"),std::string(".npy")})
            if (regular_file(stem+extension)) return stem+extension;
    }
    return "";
}

static std::vector<double> scan_values(double first,double last,int count,bool ascending) {
    std::vector<double> result;
    for (int i=0;i<count;++i) result.push_back(value_at(first,last,count,i));
    if (ascending) std::sort(result.begin(),result.end());
    return result;
}

struct TemporaryStates {
    std::vector<std::string> paths;
    ~TemporaryStates() { for (const std::string& path:paths) std::remove(path.c_str()); }
};

static int run(const Config& c,const Model& m,State& state,int threads) {
    const std::string kind=relaxation_kind(c),directory=relaxation_directory(c,kind);
    const bool coupled=c.engine=="llg" && (c.B0!=0 || c.B1!=0) && (c.E0!=0 || c.E1!=0);
    const std::string magnetic_kind=(c.T_count>1 && c.T0!=c.T1) ? "temperature_magnetic" : "magnetic";
    const std::vector<double> temperatures=scan_values(c.T0,c.T1,c.T_count,false),
        fields=scan_values(c.B0,c.B1,c.B_count,coupled),electrics=scan_values(c.E0,c.E1,c.E_count,coupled);
    directories(directory);
    save_settings(c,directory,threads);
    save_state(state,join(directory,"initial_state.txt"));
    save_checkpoint(state,directory,1,0,temperatures.front(),fields.front(),coupled ? 0 : electrics.front());
    std::ofstream trace(join(directory,"trace.csv").c_str()),summary(join(directory,"summary.csv").c_str());
    trace<<"point,T_K,B_T,Ez,steps,elapsed_s,energy_meV,Mx,My,Mz,Q,max_torque_meV,unit\n"<<std::setprecision(17);
    summary<<"point,T_K,B_T,Ez,steps,elapsed_s,energy_meV,energy_per_spin_meV,Mx,My,Mz,Q,max_torque_meV,status,snapshot,phase,source,unit,acceptance\n"<<std::setprecision(17);
    trace.flush(); summary.flush();
    const int points=c.T_count*c.B_count*(c.E_count+(coupled ? 1 : 0));
    const Clock::time_point run_start=Clock::now();
    const char* unit=c.engine=="mc" ? "sweeps" : "steps";
    std::unique_ptr<spin::Colours> colours;
    if (c.engine=="mc") {
        colours.reset(new spin::Colours(m.lattice));
        std::cout<<"[MC 并行] 三壳层安全着色，共 "<<colours->count()<<" 组；每个 sweep 每格点尝试一次\n";
    }
    std::cout<<"[输出目录] "<<directory<<"\n[构型复用] "<<(c.reuse_states ? "先读取已有完整场点，缺失时才弛豫" : "关闭，重新弛豫")<<'\n';
    if (coupled) std::cout<<"[联合扫描] 每个温度先准备纯磁场构型，再从每个磁场自己的构型分别扫电场；B/Ez 升序\n";
    int point=0;
    TemporaryStates temporary;
    const auto run_point=[&](double T,double B,double Ez,const std::string& point_kind,
                             const std::string& phase,bool need_base)->std::string {
        ++point;
        const Clock::time_point point_start=Clock::now();
        const std::string point_directory=relaxation_directory(c,point_kind);
        const std::string label=snapshot_label(T,B,Ez),stem=join(point_directory,label);
        const std::string cached=cached_state(c,point_kind,T,B,Ez);
        std::uint64_t done=0;
        double acceptance=std::numeric_limits<double>::quiet_NaN();
        double last_log=0,last_checkpoint=0;
        std::uint64_t last_steps=0;
        bool first=true;
        std::exception_ptr callback_error;
        std::cout<<'['<<c.engine<<" 点 "<<point<<'/'<<points<<"] "<<phase<<"; T="<<T<<" K, Bz="<<B<<" T, Ez="<<Ez<<'\n';
        if (!cached.empty()) {
            state=load_state(cached,m);
            std::cout<<"[构型读取] "<<cached<<"；不重新弛豫、不覆盖原构型\n";
        } else {
            std::cout<<"[构型缺失] 开始计算 "<<c.units()<<' '<<unit<<'\n';
            const auto report=[&](std::uint64_t iteration,const State& current) {
                try {
                    const double elapsed=seconds(point_start);
                    if (first || elapsed-last_log>=c.log_seconds || iteration==c.units() || received_signal) {
                        const Observables o=observe(m,current,B,Ez);
                        trace<<point<<','<<T<<','<<B<<','<<Ez<<','<<iteration<<','<<elapsed<<','<<o.energy<<','
                             <<o.magnetization.x<<','<<o.magnetization.y<<','<<o.magnetization.z<<','<<o.charge<<','<<o.torque<<','<<unit<<'\n';
                        trace.flush(); check_output(trace,join(directory,"trace.csv"));
                        std::cout<<'['<<c.engine<<" 运行点 "<<point<<'/'<<points<<"] "<<iteration<<'/'<<c.units()<<' '<<unit<<"，本点 "
                            <<100.0*iteration/c.units()<<"%，总进度 "
                            <<100.0*((point-1)+static_cast<double>(iteration)/c.units())/points<<'%';
                        if (c.engine=="llg") std::cout<<"，物理时间 "<<iteration*c.dt_fs/1000<<" ps";
                        if (!first && iteration>last_steps) {
                            const double rate=(iteration-last_steps)/std::max(elapsed-last_log,1e-12);
                            const double remaining=(c.units()-iteration+static_cast<double>(points-point)*c.units())/rate;
                            std::cout<<"，速度 "<<rate<<' '<<unit<<"/s，预计剩余 "<<remaining/3600<<" h";
                        }
                        std::cout<<"，总耗时 "<<seconds(run_start)<<" s，Q="<<o.charge<<"，E/N="<<o.energy/m.lattice.count<<" meV\n";
                        last_log=elapsed; last_steps=iteration; first=false;
                    }
                    if (elapsed-last_checkpoint>=c.checkpoint_seconds || received_signal) {
                        save_checkpoint(current,directory,point,iteration,T,B,Ez); last_checkpoint=elapsed;
                        std::cout<<"[中间保存] checkpoint.txt；点 "<<point<<"，步数 "<<iteration<<'\n';
                    }
                } catch (...) { callback_error=std::current_exception(); return true; }
                return received_signal!=0;
            };
            if (c.engine=="mc") {
                const spin::MCResult result=spin::monte_carlo(m,state,*colours,T,B,c.proposal_sigma,
                    c.equilibration,c.measurement,spin::mixed_seed(c.seed+static_cast<std::uint64_t>(point)),report);
                done=result.sweeps; acceptance=result.acceptance;
            } else done=spin::integrate(m,state,T,B,Ez,c.alpha,c.dt_fs*1e-15,c.thermal,c.steps(),
                spin::mixed_seed(c.seed+static_cast<std::uint64_t>(point)),report,0,c.reference);
            if (callback_error) std::rethrow_exception(callback_error);
        }
        save_checkpoint(state,directory,point,done,T,B,Ez);
        if (received_signal) return ""; // 中断的点仅保存 checkpoint，不能成为可复用完整场点。
        std::string base_path=cached;
        if (cached.empty()) {
            directories(point_directory);
            if (c.save_text) {
                save_state(state,stem+".txt"); base_path=stem+".txt";
            } else if (need_base) {
                base_path=join(directory,"magnetic_base_"+std::to_string(point)+".tmp.txt");
                save_state(state,base_path); temporary.paths.push_back(base_path);
            }
            if (c.png) {
                const std::string source=c.save_text ? stem+".txt" : stem+".render.tmp.txt";
                if (!c.save_text) save_state(state,source);
                render_png(c,source,stem+".png",T,B,Ez);
                if (!c.save_text) std::remove(source.c_str());
            }
        }
        if (c.save_text) {
            directories(point_directory);
            save_state(state,join(point_directory,"final_state.txt"));
            if (point_directory!=directory)
                save_state(state,join(directory,"final_state.txt"));
        }
        const Observables o=observe(m,state,B,Ez);
        // summary 位于 场分类/尺寸/；退回两层后相对 engine（或 engine/band）定位。
        // 同时支持其他场分类的新尺寸目录，以及上一版的扁平缓存路径。
        const std::string snapshot_path=!cached.empty() ? cached : (c.save_text ? stem+".txt" : "");
        const std::string snapshot=snapshot_path.empty() ? "" : "../../"+snapshot_path.substr(engine_directory(c).size()+1);
        summary<<point<<','<<T<<','<<B<<','<<Ez<<','<<done<<','<<seconds(point_start)<<','<<o.energy<<','
            <<o.energy/m.lattice.count<<','<<o.magnetization.x<<','<<o.magnetization.y<<','<<o.magnetization.z
            <<','<<o.charge<<','<<o.torque<<','<<(cached.empty() ? "completed" : "reused_state")<<','
            <<snapshot<<','<<phase<<','<<cached<<','<<unit<<',';
        if (c.engine=="mc" && cached.empty()) summary<<acceptance;
        summary<<'\n';
        summary.flush(); check_output(summary,join(directory,"summary.csv"));
        std::cout<<'['<<c.engine<<" 完成点 "<<point<<'/'<<points<<"] "<<(cached.empty() ? "已计算" : "已复用")
            <<"，Q="<<o.charge<<"，Mz="<<o.magnetization.z<<"，E/N="<<o.energy/m.lattice.count<<" meV";
        if (c.engine=="mc" && cached.empty()) std::cout<<"，测量接受率 "<<acceptance;
        std::cout<<'\n';
        return base_path;
    };
    if (coupled) {
        State magnetic_state=state;
        for (double T:temperatures) {
            state=magnetic_state;
            std::vector<std::string> bases;
            for (double B:fields) {
                bases.push_back(run_point(T,B,0,magnetic_kind,"magnetic_base",true));
                if (received_signal) return 128+received_signal;
            }
            // 下一温度只能接收纯磁场阶段的末态，电场分支不反馈进来。
            magnetic_state=state;
            for (std::size_t bi=0;bi<fields.size();++bi) {
                state=load_state(bases[bi],m);
                std::cout<<"[电场分支] Bz="<<fields[bi]<<" T，从其对应纯磁场构型开始\n";
                for (double Ez:electrics) {
                    run_point(T,fields[bi],Ez,kind,"electric_sweep",false);
                    if (received_signal) return 128+received_signal;
                }
            }
        }
    } else {
        for (double T:temperatures) for (double B:fields) for (double Ez:electrics) {
            run_point(T,B,Ez,kind,"scan",false);
            if (received_signal) return 128+received_signal;
        }
    }
    std::cout<<"[Finished] "<<directory<<"; wall time="<<seconds(run_start)<<" s\n";
    return 0;
}

#endif
