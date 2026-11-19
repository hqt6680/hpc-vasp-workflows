// 纳米带：x/y 独立设置边界；缓存优先，磁电联合扫描按原 C++ 分支逻辑执行。
#include "io.hpp"
#include "mc.hpp"
#include <memory>

struct Config {
    spin::Material material;
    std::string name,engine,boundary_x,boundary_y,initial,output,ground_state,python,plot_script,base_dir,noise_file,uniform_file,order_file;
    int nx,ny,threads,T_count,B_count,E_count;
    std::uint64_t seed,step_override,equilibration,measurement;
    double T0,T1,B0,B1,E0,E1,alpha,dt_fs,time_ps,log_seconds,checkpoint_seconds,radius,wall,proposal_sigma;
    bool thermal,png,save_text,read_ground,reference,dry_run,probe,reuse_states,mc_electric_ignored;
    Config(): name("MnInP2Te6"),engine("llg"),boundary_x("open"),boundary_y("open"),initial("random"),
        output("result"),ground_state("auto"),python("python"),
        plot_script("render_snapshot.py"),base_dir("."),nx(256),ny(64),threads(0),
        T_count(50),B_count(1),E_count(1),seed(12345),step_override(0),equilibration(5000),measurement(10),T0(200),T1(.1),
        B0(0),B1(0),E0(0),E1(0),alpha(.5),dt_fs(.1),time_ps(50),log_seconds(30),
        checkpoint_seconds(300),radius(8),wall(2),proposal_sigma(60),thermal(true),png(true),save_text(true),
        read_ground(false),reference(false),dry_run(false),probe(false),reuse_states(true),mc_electric_ignored(false) {}
    std::uint64_t steps() const {
        if (step_override) return step_override;
        const double n=std::nearbyint(time_ps*1000/dt_fs);
        if (!std::isfinite(n) || n>1e12) throw std::runtime_error("step count exceeds 1e12; check time units");
        return static_cast<std::uint64_t>(std::max(1.0,n));
    }
    std::uint64_t units() const { return engine=="mc" ? equilibration+measurement : steps(); }
};

static void setting(Config& c,const std::string& key,const std::string& value) {
    const std::map<std::string,double*> numbers={
        {"lattice_constant_angstrom",&c.material.lattice_constant},{"moment_muB",&c.material.moment},
        {"J1_meV",&c.material.J[0]},{"J2_meV",&c.material.J[1]},{"J3_meV",&c.material.J[2]},
        {"lambda_meV",&c.material.lambda},{"K_meV",&c.material.K},{"D_meV",&c.material.D},
        {"Kxy_meV",&c.material.Kxy},{"Kxz_meV",&c.material.Kxz},
        {"damping",&c.alpha},{"dt_fs",&c.dt_fs},{"relaxation_ps",&c.time_ps},
        {"temperature_start_K",&c.T0},{"temperature_end_K",&c.T1},
        {"field_start_T",&c.B0},{"field_end_T",&c.B1},{"electric_start",&c.E0},{"electric_end",&c.E1},
        {"log_interval_seconds",&c.log_seconds},{"checkpoint_interval_seconds",&c.checkpoint_seconds},
        {"skyrmion_radius_sites",&c.radius},{"skyrmion_wall_sites",&c.wall}};
    const std::map<std::string,int*> integers={
        {"Nx",&c.nx},{"Ny",&c.ny},{"length",&c.nx},{"width",&c.ny},{"cpu_threads",&c.threads},
        {"temperature_count",&c.T_count},{"field_count",&c.B_count},{"electric_count",&c.E_count}};
    const std::map<std::string,bool*> booleans={
        {"thermal_noise",&c.thermal},{"write_png",&c.png},{"save_text",&c.save_text},
        {"read_ground_state",&c.read_ground},{"reuse_states",&c.reuse_states}};
    const std::map<std::string,std::string*> strings={
        {"material_name",&c.name},{"engine",&c.engine},
        {"boundary_x",&c.boundary_x},{"boundary_y",&c.boundary_y},
        {"initial_state",&c.initial},{"ground_state_file",&c.ground_state},{"output_dir",&c.output},
        {"python_executable",&c.python},{"plot_script",&c.plot_script}};
    if (key=="proposal_sigma") c.proposal_sigma=number(value);
    else if (key=="equilibration_sweeps") c.equilibration=unsigned_integer(value);
    else if (key=="measurement_sweeps") c.measurement=unsigned_integer(value);
    else if (key=="llg_steps") c.step_override=unsigned_integer(value);
    else if (key=="boundary") c.boundary_x=c.boundary_y=value; // 兼容上一版统一边界参数。
    else if (numbers.count(key)) *numbers.at(key)=number(value);
    else if (integers.count(key)) *integers.at(key)=integer(value);
    else if (booleans.count(key)) *booleans.at(key)=boolean(value);
    else if (strings.count(key)) *strings.at(key)=value;
    else if (key=="seed") c.seed=unsigned_integer(value);
    else if (key=="llg_kernel") {
        if (value!="optimized" && value!="reference") throw std::runtime_error("llg_kernel must be optimized or reference");
        c.reference=value=="reference";
    } else if (key=="dmi_type") {
        if (value!="bloch" && value!="neel") throw std::runtime_error("dmi_type must be bloch or neel");
        c.material.neel=value=="neel";
    } else throw std::runtime_error("unknown configuration key: "+key);
}

static void load_config(Config& c,const std::string& path) {
    std::ifstream in(path.c_str());
    if (!in) throw std::runtime_error("cannot read configuration: "+path);
    std::string line;
    int index=0;
    while (std::getline(in,line)) {
        ++index;
        if (index==1 && line.compare(0,3,"\xef\xbb\xbf")==0) line.erase(0,3);
        line=trim(line.substr(0,line.find('#')));
        if (line.empty()) continue;
        const std::size_t at=line.find('=');
        if (at==std::string::npos) throw std::runtime_error("missing '=' at config line "+std::to_string(index));
        const std::string key=trim(line.substr(0,at)),value=trim(line.substr(at+1));
        if (value.empty()) throw std::runtime_error("empty value at config line "+std::to_string(index));
        setting(c,key,value);
    }
    if (!in.eof()) throw std::runtime_error("failed reading configuration: "+path);
}

static bool built_in_state(const std::string& value) {
    return value=="random" || value=="skyrmion" || value=="uniform";
}

static std::string geometry_name(const Config& c) {
    return "Nx"+std::to_string(c.nx)+"_Ny"+std::to_string(c.ny)
        +"_X"+c.boundary_x+"_Y"+c.boundary_y;
}

static std::string engine_directory(const Config& c) {
    std::string directory=join(join(c.output,c.name),c.engine);
    if (c.boundary_x=="open" || c.boundary_y=="open") directory=join(directory,"band");
    return directory;
}

// 所有 engine/场类型统一按尺寸和独立边界隔离，运行记录也保存在该目录。
static std::string relaxation_directory(const Config& c,const std::string& kind) {
    return join(join(engine_directory(c),kind),geometry_name(c));
}

static Config arguments(int argc,char** argv) {
    Config c;
    std::string path="nanoribbon.ini";
    for (int i=1;i<argc;++i) {
        if (std::string(argv[i])=="--help") {
            std::cout<<"Usage: nanoribbon_cpu [--config nanoribbon.ini] [--threads N]\n"
                <<"  --engine llg|mc (command line overrides configuration)\n"
                <<"  --length Nx --width Ny --temperature K --field T --electric Ez\n"
                <<"  --boundary-x open|periodic --boundary-y open|periodic\n"
                <<"  --temperature-sweep START END COUNT (also --field-sweep, --electric-sweep)\n"
                <<"  --random | --skyrmion | --uniform | --ground-state FILE.txt|FILE.npy\n"
                <<"  --radius A --wall A --kxy meV --kxz meV --seed N\n"
                <<"  --damping A --dt-fs fs --relaxation-ps ps --steps N --no-thermal-noise (LLG)\n"
                <<"  --equilibration-sweeps N --measurement-sweeps N --proposal-sigma S (MC only)\n"
                <<"  --thermal-noise --reuse --png --save-text --no-text\n"
                <<"  --output DIRECTORY --no-png --python EXECUTABLE --kernel optimized|reference\n"
                <<"  --no-reuse (force relaxation instead of reading completed states)\n"
                <<"  --dry-run (no result files)\n"
                <<"  --check-model [--noise-file FILE --uniform-file FILE --orders-file FILE] (validation)\n";
            std::exit(0);
        }
        if (std::string(argv[i])=="--config") {
            if (++i>=argc) throw std::runtime_error("missing --config value");
            path=argv[i];
        }
    }
    load_config(c,path);
    c.base_dir=parent_path(path);
    c.output=relative_to(c.base_dir,c.output);
    c.plot_script=relative_to(c.base_dir,c.plot_script);
    if (!built_in_state(c.initial)) c.initial=relative_to(c.base_dir,c.initial);
    if (c.ground_state!="auto") c.ground_state=relative_to(c.base_dir,c.ground_state);
    if (c.python=="python" || c.python=="python3")
        if (const char* python=std::getenv("SPIN_PLOT_PYTHON")) c.python=python;
    bool initial_override=false,steps_from_cli=false;
    for (int i=1;i<argc;++i) {
        const std::string arg=argv[i];
        if (arg=="--dry-run") { c.dry_run=true; continue; }
        if (arg=="--check-model") { c.probe=true; continue; }
        if (arg=="--no-png") { c.png=false; continue; }
        if (arg=="--png") { c.png=true; continue; }
        if (arg=="--save-text") { c.save_text=true; continue; }
        if (arg=="--no-text") { c.save_text=false; continue; }
        if (arg=="--no-reuse") { c.reuse_states=false; continue; }
        if (arg=="--reuse") { c.reuse_states=true; continue; }
        if (arg=="--no-thermal-noise") { c.thermal=false; continue; }
        if (arg=="--thermal-noise") { c.thermal=true; continue; }
        if (arg=="--random" || arg=="--skyrmion" || arg=="--uniform") {
            if (initial_override) throw std::runtime_error("initial-state options are mutually exclusive");
            initial_override=true; c.read_ground=false; c.initial=arg.substr(2); continue;
        }
        if (arg=="--temperature-sweep" || arg=="--field-sweep" || arg=="--electric-sweep") {
            if (i+3>=argc) throw std::runtime_error("expected START END COUNT after "+arg);
            const double first=number(argv[++i]),last=number(argv[++i]);
            const int count=integer(argv[++i]);
            if (arg=="--temperature-sweep") { c.T0=first; c.T1=last; c.T_count=count; }
            else if (arg=="--field-sweep") { c.B0=first; c.B1=last; c.B_count=count; }
            else { c.E0=first; c.E1=last; c.E_count=count; }
            continue;
        }
        if (++i>=argc) throw std::runtime_error("missing value for "+arg);
        const std::string value=argv[i];
        if (arg=="--config") continue;
        if (arg=="--threads" || arg=="--cpu-threads") c.threads=integer(value);
        else if (arg=="--engine") c.engine=value;
        else if (arg=="--length") c.nx=integer(value);
        else if (arg=="--width") c.ny=integer(value);
        else if (arg=="--boundary-x") c.boundary_x=value;
        else if (arg=="--boundary-y") c.boundary_y=value;
        else if (arg=="--temperature") { c.T0=c.T1=number(value); c.T_count=1; }
        else if (arg=="--field") { c.B0=c.B1=number(value); c.B_count=1; }
        else if (arg=="--electric") { c.E0=c.E1=number(value); c.E_count=1; }
        else if (arg=="--seed") c.seed=unsigned_integer(value);
        else if (arg=="--steps") {
            c.step_override=unsigned_integer(value); steps_from_cli=true;
            if (!c.step_override) throw std::runtime_error("--steps must be >=1");
        }
        else if (arg=="--equilibration-sweeps") c.equilibration=unsigned_integer(value);
        else if (arg=="--measurement-sweeps") c.measurement=unsigned_integer(value);
        else if (arg=="--proposal-sigma") c.proposal_sigma=number(value);
        else if (arg=="--radius") c.radius=number(value);
        else if (arg=="--wall") c.wall=number(value);
        else if (arg=="--kxy") c.material.Kxy=number(value);
        else if (arg=="--kxz") c.material.Kxz=number(value);
        else if (arg=="--dt-fs") c.dt_fs=number(value);
        else if (arg=="--damping") c.alpha=number(value);
        else if (arg=="--relaxation-ps") c.time_ps=number(value);
        else if (arg=="--output" || arg=="--output-dir") c.output=value;
        else if (arg=="--python") c.python=value;
        else if (arg=="--kernel") setting(c,"llg_kernel",value);
        else if (arg=="--noise-file") c.noise_file=value;
        else if (arg=="--uniform-file") c.uniform_file=value;
        else if (arg=="--orders-file") c.order_file=value;
        else if (arg=="--ground-state" || arg=="--initial-state") {
            if (initial_override) throw std::runtime_error("initial-state options are mutually exclusive");
            initial_override=true; c.initial=value; c.read_ground=false;
        } else throw std::runtime_error("unknown argument: "+arg);
    }
    if (c.engine!="llg" && c.engine!="mc") throw std::runtime_error("engine must be llg or mc");
    if (c.engine=="mc") {
        if (steps_from_cli) throw std::runtime_error("--steps is LLG-only; MC uses equilibration/measurement sweeps");
        c.mc_electric_ignored=c.E0!=0 || c.E1!=0 || c.E_count!=1;
        c.E0=c.E1=0; c.E_count=1; // 与原 MC 保持一致：电场参数不参与采样。
    }
    for (std::string* boundary:{&c.boundary_x,&c.boundary_y}) {
        if (*boundary=="closed") *boundary="open"; // 本项目“封闭”指无跨边界键的自由边界。
        if (*boundary!="open" && *boundary!="periodic") throw std::runtime_error("boundary_x/y must be open or periodic");
    }
    if (c.boundary_y=="periodic" && c.ny%2) throw std::runtime_error("periodic y boundary requires even Ny");
    if (c.name.empty() || c.name.find_first_of("/\\,\r\n")!=std::string::npos || c.name=="." || c.name=="..")
        throw std::runtime_error("material_name must be a single directory name");
    spin::Lattice::checked_count(c.nx,c.ny);
    if (c.threads<0 || c.T_count<1 || c.B_count<1 || c.E_count<1 ||
        c.T_count>100000 || c.B_count>100000 || c.E_count>100000 ||
        static_cast<std::uint64_t>(c.T_count)*c.B_count*c.E_count>100000)
        throw std::runtime_error("invalid threads or scan counts (at most 100000 conditions)");
    if ((c.T_count==1 && c.T0!=c.T1) || (c.B_count==1 && c.B0!=c.B1) || (c.E_count==1 && c.E0!=c.E1))
        throw std::runtime_error("count=1 requires equal scan endpoints");
    if (c.T0<0 || c.T1<0 ||
        c.material.moment<=0 || c.material.lattice_constant<=0 || c.log_seconds<=0 || c.checkpoint_seconds<=0)
        throw std::runtime_error("invalid physical parameter, temperature or reporting interval");
    if (c.engine=="llg") {
        if (c.alpha<0 || c.dt_fs<=0 || c.time_ps<0) throw std::runtime_error("invalid LLG damping, dt_fs or relaxation_ps");
        if (c.step_override>UINT64_C(1000000000000)) throw std::runtime_error("too many LLG steps (>1e12)");
        c.steps();
    } else if (c.T0<=0 || c.T1<=0 || !c.measurement || c.equilibration>1000000000 || c.measurement>1000000000 || c.proposal_sigma<=0)
        throw std::runtime_error("MC requires T>0, equilibration>=0, measurement>=1 and proposal_sigma>0 (sweeps <=1e9)");
    if ((!c.noise_file.empty() || !c.uniform_file.empty() || !c.order_file.empty()) && !c.probe)
        throw std::runtime_error("prescribed random files require --check-model");
    if (c.engine=="llg" && (!c.uniform_file.empty() || !c.order_file.empty())) throw std::runtime_error("uniform/orders files are MC-only");
    if (c.output.empty() || c.python.empty()) throw std::runtime_error("output and python_executable cannot be empty");
    if (c.ground_state=="auto") {
        c.ground_state=join(relaxation_directory(c,"temperature"),"final_state.txt");
        // 仅回退到上一版明确包含同尺寸/边界的文件，避免读取通用 final_state 别名。
        const std::string legacy=join(join(engine_directory(c),"temperature"),
            geometry_name(c)+"_temperature_relaxation_final_state.txt");
        if (!regular_file(c.ground_state) && regular_file(legacy)) c.ground_state=legacy;
    }
    if (c.read_ground) c.initial=c.ground_state;
    if (c.initial=="skyrmion" && (c.radius<=0 || c.wall<=0)) throw std::runtime_error("skyrmion radius/wall must be positive");
    return c;
}

#include "render_process.hpp"

static State load_state(const std::string& path,const Model& m) {
    const std::size_t extension=path.find_last_of('.');
    std::string suffix=extension==std::string::npos ? "" : path.substr(extension);
    std::transform(suffix.begin(),suffix.end(),suffix.begin(),[](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
    if (suffix!=".txt" && suffix!=".npy") throw std::runtime_error("state must be .txt or .npy: "+path);
    State state=suffix==".npy" ? spin::read_npy(path,m.lattice.nx,m.lattice.ny) : read_vectors(path);
    if (state.size()!=static_cast<std::size_t>(m.lattice.count)) throw std::runtime_error("state row count must equal Nx*Ny: "+path);
    for (Vec& s:state) {
        const double norm=std::sqrt(spin::dot(s,s));
        if (!std::isfinite(norm) || norm<1e-30) throw std::runtime_error("invalid spin length: "+path);
        s=spin::unit(s);
    }
    return state;
}

static State initial_state(const Config& c,const Model& m) {
    if (c.initial=="random") return spin::random_state(m.lattice.count,c.seed);
    if (c.initial=="uniform") return State(m.lattice.count,Vec(0,0,1));
    if (c.initial!="skyrmion") return load_state(c.initial,m);
    State state(m.lattice.count);
    const double pi=std::acos(-1.0),r=std::sqrt(3.0)/2;
    const double cx=.5*(c.nx-.5),cy=.5*(c.ny-1)*r;
    for (int i=0;i<c.nx;++i) for (int j=0;j<c.ny;++j) {
        const double x=i+.5*(j&1)-cx,y=j*r-cy;
        const double theta=pi*(1-std::tanh((std::hypot(x,y)-c.radius)/c.wall))/(1+std::tanh(c.radius/c.wall));
        const double phi=std::atan2(y,x)+(c.material.neel ? 0 : pi/2);
        state[i*c.ny+j]=Vec(std::sin(theta)*std::cos(phi),std::sin(theta)*std::sin(phi),std::cos(theta));
    }
    return state;
}

static double solid_angle(const Vec& a,const Vec& b,const Vec& c) {
    return 2*std::atan2(spin::dot(a,spin::cross(b,c)),1+spin::dot(a,b)+spin::dot(b,c)+spin::dot(c,a));
}

static double topological_charge(const State& state,const spin::Lattice& lattice) {
    double area=0;
    const int imax=lattice.periodic_x ? lattice.nx : lattice.nx-1;
    const int jmax=lattice.periodic_y ? lattice.ny : lattice.ny-1;
    for (int i=0;i<imax;++i) for (int j=0;j<jmax;++j) {
        const int next_i=(i+1)%lattice.nx,next_j=(j+1)%lattice.ny;
        const Vec &a=state[i*lattice.ny+j],&b=state[next_i*lattice.ny+j],
                  &c=state[i*lattice.ny+next_j],&d=state[next_i*lattice.ny+next_j];
        area+=(j&1) ? solid_angle(a,b,d)+solid_angle(a,d,c) : solid_angle(a,b,c)+solid_angle(b,d,c);
    }
    return area/(4*std::acos(-1.0));
}

struct Observables { double energy,torque,charge; Vec magnetization; };
static Observables observe(const Model& m,const State& state,double B,double Ez) {
    Observables o;
    o.energy=m.energy_serial(state,B,Ez); o.torque=0; o.charge=topological_charge(state,m.lattice);
    for (int i=0;i<m.lattice.count;++i) {
        const Vec& s=state[i];
        if (!std::isfinite(spin::dot(s,s))) throw std::runtime_error("non-finite spin configuration");
        o.magnetization=o.magnetization+s;
        const Vec torque=spin::cross(s,m.field_mev(state,i,B,Ez));
        o.torque=std::max(o.torque,std::sqrt(spin::dot(torque,torque)));
    }
    o.magnetization=o.magnetization*(1.0/m.lattice.count);
    if (!std::isfinite(o.energy) || !std::isfinite(o.charge)) throw std::runtime_error("non-finite model observables");
    return o;
}

static double value_at(double first,double last,int count,int i) {
    return count==1 || i==0 ? first : (i==count-1 ? last : first+(last-first)*i/(count-1));
}

static std::string relaxation_kind(const Config& c) {
    const bool magnetic=c.B0!=0 || c.B1!=0,electric=c.E0!=0 || c.E1!=0;
    const bool thermal=(c.T_count>1 && c.T0!=c.T1) || !(magnetic || electric);
    std::string category=thermal ? "temperature" : "";
    if (magnetic) category+=(category.empty() ? "" : "_")+std::string("magnetic");
    if (electric) category+=(category.empty() ? "" : "_")+std::string("electric");
    return category;
}

// 最短的可往返 double 标签：0.1 保持为 0.1，微小差值也不会因四舍五入覆盖。
static std::string number_label(double value) {
    if (value==0) return "0";
    for (int precision=1;precision<=17;++precision) {
        std::ostringstream out; out<<std::setprecision(precision)<<value;
        std::istringstream in(out.str()); double parsed=0; in>>parsed;
        if (in && parsed==value) return out.str();
    }
    throw std::runtime_error("cannot format field label");
}

static std::string snapshot_label(double T,double B,double Ez) {
    return "T_"+number_label(T)+"K_B_"+number_label(B)
        +"T_Ez_"+number_label(Ez);
}

static void save_settings(const Config& c,const std::string& directory,int threads) {
    const std::string path=join(directory,"run_settings.ini");
    std::ofstream out(path.c_str());
    out<<std::setprecision(17)
       <<"# Cache first. Coupled B/E: magnetic bases, then independent electric branches.\n"
       <<"# Values below are effective values AFTER command-line and method selection.\n"
       <<"material_name = "<<c.name<<"\nengine = "<<c.engine<<"\nboundary_x = "<<c.boundary_x<<"\nboundary_y = "<<c.boundary_y
       <<"\nNx = "<<c.nx<<"\nNy = "<<c.ny
       <<"\nlattice_constant_angstrom = "<<c.material.lattice_constant<<"\nmoment_muB = "<<c.material.moment
       <<"\nJ1_meV = "<<c.material.J[0]<<"\nJ2_meV = "<<c.material.J[1]<<"\nJ3_meV = "<<c.material.J[2]
       <<"\nlambda_meV = "<<c.material.lambda<<"\nK_meV = "<<c.material.K<<"\nD_meV = "<<c.material.D
       <<"\ndmi_type = "<<(c.material.neel ? "neel" : "bloch")<<"\nKxy_meV = "<<c.material.Kxy<<"\nKxz_meV = "<<c.material.Kxz
       <<"\ncpu_threads = "<<threads<<"\nseed = "<<c.seed<<"\ninitial_state = "<<c.initial
       <<"\nskyrmion_radius_sites = "<<c.radius<<"\nskyrmion_wall_sites = "<<c.wall
       <<"\nread_ground_state = "<<(c.read_ground ? "true" : "false")<<"\nground_state_file = "<<c.ground_state
       <<"\nllg_kernel = "<<(c.reference ? "reference" : "optimized")
       <<"\nllg_steps = "<<c.step_override
       <<"\ndamping = "<<c.alpha<<"\ndt_fs = "<<c.dt_fs<<"\nrelaxation_ps = "<<c.time_ps
       <<"\nthermal_noise = "<<(c.thermal ? "true" : "false")
       <<"\n# MC-only settings (inactive for LLG)\n"
       <<"equilibration_sweeps = "<<c.equilibration<<"\nmeasurement_sweeps = "<<c.measurement
       <<"\nproposal_sigma = "<<c.proposal_sigma
       <<"\nreuse_states = "<<(c.reuse_states ? "true" : "false")
       <<"\nsave_text = "<<(c.save_text ? "true" : "false")<<"\nwrite_png = "<<(c.png ? "true" : "false")
       <<"\npython_executable = "<<c.python<<"\nplot_script = "<<c.plot_script
       <<"\noutput_dir = "<<c.output<<"\nlog_interval_seconds = "<<c.log_seconds
       <<"\ncheckpoint_interval_seconds = "<<c.checkpoint_seconds
       <<"\ntemperature_start_K = "<<c.T0<<"\ntemperature_end_K = "<<c.T1<<"\ntemperature_count = "<<c.T_count
       <<"\nfield_start_T = "<<c.B0<<"\nfield_end_T = "<<c.B1<<"\nfield_count = "<<c.B_count
       <<"\nelectric_start = "<<c.E0<<"\nelectric_end = "<<c.E1<<"\nelectric_count = "<<c.E_count
       <<"\n# Effective iterations per point: "<<c.units()<<' '<<(c.engine=="mc" ? "sweeps" : "steps")<<'\n';
    out.close(); check_output(out,path);
}

static std::vector<double> read_scalars(const std::string& path) {
    std::ifstream in(path.c_str());
    if (!in) throw std::runtime_error("cannot read scalar file: "+path);
    std::vector<double> values;
    double value;
    while (in>>value) {
        if (!std::isfinite(value)) throw std::runtime_error("non-finite scalar in "+path);
        values.push_back(value);
    }
    if (!in.eof()) throw std::runtime_error("invalid scalar file: "+path);
    return values;
}

// --check-model 导出有效场及指定随机数轨迹，验证时使用；生产不读取外部随机数。
static void probe(const Config& c,const Model& m,State& state) {
    directories(c.output);
    const Observables initial=observe(m,state,c.B0,c.E0);
    save_state(m.fields(state,c.B0,c.E0),join(c.output,"field_meV.txt"));
    State noise;
    if (!c.noise_file.empty()) {
        noise=read_vectors(c.noise_file);
        if (c.units()>std::numeric_limits<std::size_t>::max()/state.size() || noise.size()!=c.units()*state.size())
            throw std::runtime_error("noise must contain iterations*Nx*Ny rows in standard-normal units");
    }
    double acceptance=std::numeric_limits<double>::quiet_NaN();
    if (c.engine=="mc") {
        const spin::Colours colours(m.lattice);
        std::vector<double> uniforms;
        std::vector<int> orders;
        if (!c.uniform_file.empty()) {
            uniforms=read_scalars(c.uniform_file);
            if (c.units()>std::numeric_limits<std::size_t>::max()/state.size() || uniforms.size()!=c.units()*state.size())
                throw std::runtime_error("uniform file must contain sweeps*Nx*Ny values");
            for (double draw:uniforms) if (draw<0 || draw>=1) throw std::runtime_error("uniform values must be in [0,1)");
        }
        if (!c.order_file.empty()) {
            const std::vector<double> raw=read_scalars(c.order_file);
            const std::size_t groups=static_cast<std::size_t>(colours.count());
            if (c.units()>std::numeric_limits<std::size_t>::max()/groups || raw.size()!=c.units()*groups)
                throw std::runtime_error("orders file must contain sweeps*colour_groups integers");
            for (std::uint64_t sweep=0;sweep<c.units();++sweep) {
                std::vector<bool> seen(groups,false);
                for (std::size_t q=0;q<groups;++q) {
                    const double value=raw[sweep*groups+q];
                    if (value<0 || value>=groups || value!=std::floor(value) || seen[static_cast<std::size_t>(value)])
                        throw std::runtime_error("each MC order must be a permutation of colour groups");
                    seen[static_cast<std::size_t>(value)]=true;
                    orders.push_back(static_cast<int>(value));
                }
            }
        }
        for (const std::string& name:{std::string("colours"),std::string("sites"),std::string("offsets")}) {
            const std::vector<int>& values=name=="colours" ? colours.labels : (name=="sites" ? colours.sites : colours.offsets);
            const std::string path=join(c.output,name+".txt");
            std::ofstream out(path.c_str());
            for (int value:values) out<<value<<'\n';
            out.close(); check_output(out,path);
        }
        const spin::MCResult result=spin::monte_carlo(m,state,colours,c.T0,c.B0,c.proposal_sigma,
            c.equilibration,c.measurement,c.seed,[](std::uint64_t,const State&) { return false; },
            noise.empty() ? 0 : &noise,uniforms.empty() ? 0 : &uniforms,orders.empty() ? 0 : &orders);
        acceptance=result.acceptance;
    } else spin::integrate(m,state,c.T0,c.B0,c.E0,c.alpha,c.dt_fs*1e-15,c.thermal,c.steps(),c.seed,
        [](std::uint64_t,const State&) { return false; },noise.empty() ? 0 : &noise,c.reference);
    save_state(state,join(c.output,"final_state.txt"));
    std::ofstream info(join(c.output,"probe.txt").c_str());
    info<<std::setprecision(17)<<"initial_energy_meV "<<initial.energy<<"\ninitial_Q "<<initial.charge
        <<"\nfinal_energy_meV "<<m.energy_serial(state,c.B0,c.E0)<<'\n';
    if (c.engine=="mc") info<<"acceptance "<<acceptance<<'\n';
    info.close(); check_output(info,join(c.output,"probe.txt"));
    std::ofstream neighbours(join(c.output,"neighbours.txt").c_str());
    for (const auto& near:m.lattice.neighbours) {
        for (int k=0;k<18;++k) neighbours<<(k ? " " : "")<<near[k];
        neighbours<<'\n';
    }
    neighbours.close(); check_output(neighbours,join(c.output,"neighbours.txt"));
}

#include "relaxation.hpp"

int main(int argc,char** argv) {
    std::cout.setf(std::ios::unitbuf); std::cerr.setf(std::ios::unitbuf);
    std::signal(SIGINT,on_signal); std::signal(SIGTERM,on_signal);
    try {
        const Config c=arguments(argc,argv);
        const int threads=setup_threads(c.threads);
        const Model model(c.material,c.nx,c.ny,c.boundary_x=="periodic",c.boundary_y=="periodic");
        State state=initial_state(c,model);
        std::cout<<"[C++/OpenMP 纳米带] "<<c.name<<"; Nx="<<c.nx<<", Ny="<<c.ny
            <<"; boundary_x="<<c.boundary_x<<", boundary_y="<<c.boundary_y<<'\n'
            <<"[材料] J1/J2/J3="<<c.material.J[0]<<'/'<<c.material.J[1]<<'/'<<c.material.J[2]
            <<" meV; lambda="<<c.material.lambda<<"; K="<<c.material.K<<"; D="<<c.material.D
            <<"; DMI="<<(c.material.neel ? "neel" : "bloch")<<"; Kxy/Kxz="<<c.material.Kxy<<'/'<<c.material.Kxz<<'\n';
        if (c.engine=="llg") std::cout<<"[LLG] 随机 Heun; 阻尼="<<c.alpha<<"; dt="<<c.dt_fs<<" fs; "<<c.steps()
            <<" steps/point; 热噪声="<<c.thermal<<"; 内核="<<(c.reference ? "reference" : "optimized")<<'\n';
        else std::cout<<"[MC] Metropolis; 平衡="<<c.equilibration<<", 测量="<<c.measurement
            <<" sweeps; 提议宽度="<<c.proposal_sigma<<"; 每点共 "<<c.units()<<" sweeps\n"
            <<"[MC 参数作用] 温度进入接受概率；电场和 LLG 的时间步长、阻尼、热噪声开关不参与 MC\n";
        std::cout<<"[初态] "<<c.initial<<"; seed="<<c.seed<<"\n[扫描] T="<<c.T0<<" -> "<<c.T1<<" K ("<<c.T_count
            <<"), Bz="<<c.B0<<" -> "<<c.B1<<" T ("<<c.B_count<<"), Ez="<<c.E0<<" -> "<<c.E1<<" ("<<c.E_count<<")\n";
        if (c.mc_electric_ignored) std::cout<<"[MC 电场] 配置/命令行中的电场扫描已忽略，实际 Ez=0、点数=1，与原 MC 一致\n";
        if (c.engine=="llg" && (c.E0!=0 || c.E1!=0) && c.material.Kxy==0 && c.material.Kxz==0)
            std::cout<<"[提示] 沿用原材料参数 Kxy=Kxz=0，电场不会改变动力学；按材料数据设置非零耦合后才生效。\n";
        if (c.dry_run) { std::cout<<"[Dry run] Configuration and initial state valid; no results written\n"; return 0; }
        if (c.probe) { probe(c,model,state); return 0; }
        return run(c,model,state,threads);
    } catch (const std::exception& error) {
        std::cerr<<"[Error] "<<error.what()<<'\n'; return 1;
    }
}
