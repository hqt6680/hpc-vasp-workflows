#ifndef NANORIBBON_RENDER_PROCESS_HPP
#define NANORIBBON_RENDER_PROCESS_HPP
static std::string precise_number(double number) {
    std::ostringstream value; value<<std::setprecision(17)<<number; return value.str();
}
static void render_png(const Config& c,const std::string& source,const std::string& target,double T,double B,double Ez) {
    std::vector<std::string> arguments={c.python,c.plot_script,"--state",source,"--output",target,
        "--length",std::to_string(c.nx),"--width",std::to_string(c.ny),"--temperature",precise_number(T),"--field",precise_number(B),
        "--electric",precise_number(Ez),"--engine",c.engine,
        "--boundary-x",c.boundary_x,"--boundary-y",c.boundary_y};
    std::vector<char*> pointers;
    #ifdef _WIN32
    // Windows CRT 的 spawn 要求包含空格的参数带引号；没有 shell 参与。
    for (std::string& arg : arguments) if (arg.find_first_of(" \t")!=std::string::npos) arg="\""+arg+"\"";
    #endif
    for (std::string& arg : arguments) pointers.push_back(&arg[0]);
    pointers.push_back(0);
    int status=0;
    #ifdef _WIN32
    // 配置文件使用 UTF-8，Windows 用宽字符进程接口保留中文目录。
    std::wstring_convert<std::codecvt_utf8_utf16<wchar_t> > converter;
    std::vector<std::wstring> wide_arguments;
    for (const std::string& arg : arguments) wide_arguments.push_back(converter.from_bytes(arg));
    std::vector<const wchar_t*> wide_pointers;
    for (const std::wstring& arg : wide_arguments) wide_pointers.push_back(arg.c_str());
    wide_pointers.push_back(0);
    const std::wstring executable=converter.from_bytes(c.python);
    status=static_cast<int>(_wspawnvp(_P_WAIT,executable.c_str(),wide_pointers.data()));
    #else
    const pid_t process=fork();
    if (process<0) throw std::runtime_error("cannot start PNG renderer");
    if (process==0) {
        execvp(pointers[0],pointers.data());
        const char message[]="Cannot execute PNG Python; set python_executable or write_png=false.\n";
        const ssize_t ignored=write(STDERR_FILENO,message,sizeof(message)-1); (void)ignored;
        _exit(127);
    }
    int wait_status=0;
    while (waitpid(process,&wait_status,0)<0) if (errno!=EINTR) throw std::runtime_error("cannot wait for PNG renderer");
    status=WIFEXITED(wait_status) ? WEXITSTATUS(wait_status) : 128+WTERMSIG(wait_status);
    #endif
    if (status!=0) throw std::runtime_error("PNG renderer failed; spin TXT/checkpoint saved. Check python_executable and existing NumPy/Matplotlib");
}

#endif
