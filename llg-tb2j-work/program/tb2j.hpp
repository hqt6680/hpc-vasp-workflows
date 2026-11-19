#ifndef SPIN_TB2J_HPP
#define SPIN_TB2J_HPP

#include <array>
#include <cmath>
#include <fstream>
#include <limits>
#include <locale>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace spin {

struct Tb2jBond {
    int r1, r2;
    double distance, j;
    std::array<double, 3> d;
    std::array<double, 9> ani;
};

namespace tb2j_detail {

inline std::string trim(const std::string& s) {
    const auto begin=s.find_first_not_of(" \t\r\n");
    if (begin==std::string::npos) return {};
    return s.substr(begin,s.find_last_not_of(" \t\r\n")-begin+1);
}

inline std::vector<std::string> split(const std::string& line) {
    std::vector<std::string> values;
    std::size_t start=0;
    for (;;) {
        const auto comma=line.find(',',start);
        values.push_back(trim(line.substr(start,comma-start)));
        if (comma==std::string::npos) return values;
        start=comma+1;
    }
}

template<class T>
inline T number(const std::string& value,const char* column) {
    std::istringstream in(value);
    in.imbue(std::locale::classic());
    T result;
    if (!(in >> result) || !in.eof() || !std::isfinite(result))
        throw std::runtime_error(std::string("invalid numeric value in ")+column);
    return result;
}

inline bool equal_mev(double lhs,double rhs) {
    return std::abs(lhs-rhs)<=1e-5;
}

inline double twice(double value) {
    if (std::abs(value)>std::numeric_limits<double>::max()/2)
        throw std::runtime_error("TB2J exchange coefficient overflows after conversion");
    return 2*value;
}

} // namespace tb2j_detail

inline std::vector<Tb2jBond> load_tb2j_bonds(const std::string& path,double lattice_constant) {
    using namespace tb2j_detail;
    if (!std::isfinite(lattice_constant) || lattice_constant<=0)
        throw std::runtime_error("TB2J requires a positive lattice constant in angstroms");

    std::ifstream file(path);
    std::string line;
    if (!std::getline(file,line)) throw std::runtime_error("Cannot read TB2J CSV: "+path);
    if (line.compare(0,3,"\xEF\xBB\xBF")==0) line.erase(0,3);
    const auto columns=split(line);
    std::map<std::string,std::size_t> positions;
    for (std::size_t i=0;i<columns.size();++i)
        if (columns[i].empty() || !positions.emplace(columns[i],i).second)
            throw std::runtime_error("Empty or repeated column in TB2J CSV: "+path);

    const auto column=[&](const char* name) {
        const auto pos=positions.find(name);
        if (pos==positions.end())
            throw std::runtime_error(path+": missing TB2J column "+name);
        return pos->second;
    };
    const auto atom_i=column("i"),atom_j=column("j");
    const auto r1=column("R1"),r2=column("R2"),r3=column("R3");
    const auto distance=column("distance_angstrom"),j=column("Jiso_meV");
    const char* const d_names[]={"Dx_meV","Dy_meV","Dz_meV"};
    const char* const ani_names[]={
        "Jani_xx_meV","Jani_xy_meV","Jani_xz_meV",
        "Jani_yx_meV","Jani_yy_meV","Jani_yz_meV",
        "Jani_zx_meV","Jani_zy_meV","Jani_zz_meV"
    };
    std::array<std::size_t,3> d_cols;
    std::array<std::size_t,9> ani_cols;
    for (std::size_t n=0;n<d_cols.size();++n) d_cols[n]=column(d_names[n]);
    for (std::size_t n=0;n<ani_cols.size();++n) ani_cols[n]=column(ani_names[n]);

    std::vector<Tb2jBond> bonds;
    std::map<std::pair<int,int>,std::size_t> index;
    std::string site;
    for (std::size_t row=2;std::getline(file,line);++row) {
        if (trim(line).empty()) continue;
        const auto values=split(line);
        try {
            if (values.size()!=columns.size()) throw std::runtime_error("incorrect column count");
            if (site.empty()) site=values[atom_i];
            if (site.empty() || values[atom_i]!=site || values[atom_j]!=site)
                throw std::runtime_error("only one magnetic sublattice is supported");
            Tb2jBond bond;
            bond.r1=number<int>(values[r1],"R1");
            bond.r2=number<int>(values[r2],"R2");
            if (bond.r1 < -1000 || bond.r1 > 1000 || bond.r2 < -1000 || bond.r2 > 1000)
                throw std::runtime_error("in-plane translation exceeds 1000 cells");
            if (number<int>(values[r3],"R3")!=0 || (bond.r1==0 && bond.r2==0))
                throw std::runtime_error("only nonzero in-plane translations are supported");

            bond.distance=number<double>(values[distance],"distance_angstrom");
            const double a=bond.r1,b=bond.r2;
            const double expected=lattice_constant*std::sqrt(a*a-a*b+b*b);
            if (!(bond.distance>0) || !std::isfinite(expected) || std::abs(bond.distance-expected)>1e-4)
                throw std::runtime_error("bond distance does not match the triangular lattice constant");
            bond.j=number<double>(values[j],"Jiso_meV");
            for (std::size_t n=0;n<bond.d.size();++n)
                bond.d[n]=number<double>(values[d_cols[n]],d_names[n]);
            for (std::size_t n=0;n<bond.ani.size();++n)
                bond.ani[n]=number<double>(values[ani_cols[n]],ani_names[n]);
            for (int x=0;x<3;++x)
                for (int y=x+1;y<3;++y)
                    if (!equal_mev(bond.ani[3*x+y],bond.ani[3*y+x]))
                        throw std::runtime_error("anisotropic exchange tensor is not symmetric");
            if (!index.emplace(std::make_pair(bond.r1,bond.r2),bonds.size()).second)
                throw std::runtime_error("repeated directed translation");
            bonds.push_back(bond);
        } catch (const std::runtime_error& e) {
            throw std::runtime_error(path+":"+std::to_string(row)+": "+e.what());
        }
    }
    if (!file.eof() || bonds.empty()) throw std::runtime_error("No complete TB2J data in "+path);

    for (const auto& bond : bonds) {
        const auto opposite=index.find(std::make_pair(-bond.r1,-bond.r2));
        const std::string pair=" for ("+std::to_string(bond.r1)+", "+std::to_string(bond.r2)+") in "+path;
        if (opposite==index.end()) throw std::runtime_error("Missing reverse TB2J bond"+pair);
        const auto& reverse=bonds[opposite->second];
        if (!equal_mev(bond.j,reverse.j)) throw std::runtime_error("Inconsistent reverse J"+pair);
        for (int x=0;x<3;++x) {
            if (!equal_mev(bond.d[x],-reverse.d[x])) throw std::runtime_error("Inconsistent reverse DMI"+pair);
            for (int y=0;y<3;++y)
                if (!equal_mev(bond.ani[3*x+y],reverse.ani[3*y+x]))
                    throw std::runtime_error("Inconsistent reverse anisotropic exchange"+pair);
        }
    }

    // The LLG energy counts each physical bond once, while raw TB2J counts both directions.
    for (auto& bond : bonds) {
        bond.j=twice(bond.j);
        for (auto& value : bond.d) value=twice(value);
        for (auto& value : bond.ani) value=twice(value);
    }
    return bonds;
}

} // namespace spin

#endif
