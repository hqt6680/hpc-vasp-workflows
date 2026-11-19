#ifndef MNINP2TE6_NPY_HPP
#define MNINP2TE6_NPY_HPP
#include "physics.hpp"
#include <cstring>
#include <fstream>
#include <limits>
#include <sstream>

namespace spin {
// 直接读取 NumPy 文件，不调用 Python、不加载 pickle。
// 支持标准实数/整数、大小端、C/Fortran 排列及 NPY 1/2/3 版本。
inline std::string npy_value(const std::string& header,const std::string& key) {
    std::size_t at=header.find("'"+key+"'");
    if (at==std::string::npos) at=header.find("\""+key+"\"");
    if (at==std::string::npos || (at=header.find(':',at))==std::string::npos)
        throw std::runtime_error("missing NPY header key: "+key);
    return header.substr(at+1);
}
inline State read_npy(const std::string& path,int nx,int ny) {
    std::ifstream in(path.c_str(),std::ios::binary);
    char magic[8]; in.read(magic,8);
    if (!in || std::memcmp(magic,"\x93NUMPY",6)!=0 || magic[7]!=0 || magic[6]<1 || magic[6]>3)
        throw std::runtime_error("invalid or unsupported NPY header: "+path);
    const int size=magic[6]==1 ? 2 : 4;
    unsigned char length_bytes[4]={0}; in.read(reinterpret_cast<char*>(length_bytes),size);
    std::uint32_t length=0;
    for (int k=0;k<size;++k) length|=static_cast<std::uint32_t>(length_bytes[k])<<(8*k);
    if (!in || length>1048576) throw std::runtime_error("invalid NPY header length");
    std::string header(length,' '); in.read(&header[0],length);
    if (!in) throw std::runtime_error("truncated NPY header");
    const std::string descriptor=npy_value(header,"descr");
    const std::size_t quote=descriptor.find_first_not_of(" \t");
    if (quote==std::string::npos || (descriptor[quote]!='\'' && descriptor[quote]!='\"'))
        throw std::runtime_error("NPY structured/object dtypes are not spin arrays");
    const std::size_t close=descriptor.find(descriptor[quote],quote+1);
    const std::string dtype=descriptor.substr(quote+1,close-quote-1);
    if (close==std::string::npos || dtype.size()<3) throw std::runtime_error("invalid NPY dtype");
    const char order=dtype[0],kind=dtype[1];
    const int width=std::stoi(dtype.substr(2));
    if ((order!='<' && order!='>' && order!='=' && order!='|') ||
        !((kind=='f' && (width==2 || width==4 || width==8)) ||
          ((kind=='i' || kind=='u') && (width==1 || width==2 || width==4 || width==8)) ||
          (kind=='b' && width==1))) throw std::runtime_error("unsupported NPY spin dtype: "+dtype);
    const std::string shape=npy_value(header,"shape");
    const std::size_t left=shape.find('('),right=shape.find(')',left);
    if (left==std::string::npos || right==std::string::npos) throw std::runtime_error("invalid NPY shape");
    std::string dimensions=shape.substr(left+1,right-left-1);
    std::replace(dimensions.begin(),dimensions.end(),',',' ');
    std::istringstream dimension_stream(dimensions);
    std::vector<int> dims; int dimension;
    while (dimension_stream>>dimension) dims.push_back(dimension);
    if (!dimension_stream.eof() || !((dims.size()==3 && dims[0]==nx && dims[1]==ny && dims[2]==3) ||
        (dims.size()==2 && dims[0]==nx*ny && dims[1]==3)))
        throw std::runtime_error("NPY spin shape must be (Nx,Ny,3) or (Nx*Ny,3)");
    const std::string fortran_value=npy_value(header,"fortran_order");
    const std::size_t first=fortran_value.find_first_not_of(" \t");
    const bool fortran=fortran_value.compare(first,4,"True")==0;
    if (!fortran && fortran_value.compare(first,5,"False")!=0) throw std::runtime_error("invalid NPY array order");
    const std::uint16_t endian_test=1;
    const bool native_little=*reinterpret_cast<const unsigned char*>(&endian_test)==1;
    const bool little=order=='<' || (order!='>' && native_little);
    State result(nx*ny);
    for (std::size_t element=0;element<result.size()*3;++element) {
        unsigned char bytes[8]={0}; in.read(reinterpret_cast<char*>(bytes),width);
        if (!in) throw std::runtime_error("truncated NPY array data");
        std::uint64_t raw=0;
        for (int k=0;k<width;++k) raw|=static_cast<std::uint64_t>(bytes[little ? k : width-1-k])<<(8*k);
        double value=0;
        if (kind=='f' && width==8) std::memcpy(&value,&raw,8);
        else if (kind=='f' && width==4) {
            const std::uint32_t bits=static_cast<std::uint32_t>(raw); float f;
            std::memcpy(&f,&bits,4); value=f;
        } else if (kind=='f') {
            // IEEE binary16：避免引入平台相关的半精度编译器扩展。
            const int exponent=static_cast<int>((raw>>10)&31),mantissa=static_cast<int>(raw&1023);
            value=exponent==31 ? (mantissa ? std::numeric_limits<double>::quiet_NaN() : std::numeric_limits<double>::infinity()) :
                std::ldexp(exponent ? 1024.0+mantissa : static_cast<double>(mantissa),exponent ? exponent-25 : -24);
            if (raw&32768) value=-value;
        } else if (kind=='i') {
            if (width<8 && (raw&(UINT64_C(1)<<(width*8-1)))) raw|=(~UINT64_C(0))<<(width*8);
            std::int64_t signed_value; std::memcpy(&signed_value,&raw,8); value=static_cast<double>(signed_value);
        } else value=kind=='b' ? raw!=0 : static_cast<double>(raw);
        if (!std::isfinite(value)) throw std::runtime_error("NPY contains NaN/infinite spin components");
        std::size_t site,component;
        if (!fortran) { site=element/3; component=element%3; }
        else {
            component=element/(nx*ny);
            if (dims.size()==2) site=element%(nx*ny);
            else { const std::size_t plane=element%(nx*ny); site=(plane%nx)*ny+plane/nx; }
        }
        if (component==0) result[site].x=value;
        else if (component==1) result[site].y=value;
        else result[site].z=value;
    }
    return result;
}
} // namespace spin
#endif
