#pragma once
#include "HttpAccessPolicy.h"

namespace heating::control {
// Match only real compiled assets (including their existing gzip aliases).
// Unknown/API paths remain outside this handler and keep their normal errors.
template<class Assets>
bool embeddedAssetPath(std::string_view path,const Assets &assets) {
    if(!safeStaticPath(path))return false;
    for(const auto &asset:assets) {
        const std::string_view stored=asset.path;
        if(path==stored||(stored.size()>3&&stored.substr(stored.size()-3)==".gz"&&
                         path==stored.substr(0,stored.size()-3)))return true;
    }
    return false;
}
}
