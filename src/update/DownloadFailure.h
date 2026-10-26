#pragma once
#include <string>
#include <string_view>

namespace heating::update {
// Volatile diagnostics only. Keep signed redirect paths, query strings and
// library error text out of the status response. A negative HTTPClient result
// is a local transport result, never an HTTP response from GitHub.
struct DownloadFailure {
    const char *kind="none", *host="";
    int httpStatus=0, clientCode=0, tlsCode=0;
};
inline const char *downloadHost(std::string_view url) {
    if(url.substr(0,8)!="https://")return "";
    url.remove_prefix(8);
    const auto slash=url.find('/');if(slash==std::string_view::npos)return "";
    const auto authority=url.substr(0,slash);
    for(const auto host:{"api.github.com","github.com","release-assets.githubusercontent.com","objects.githubusercontent.com"}) {
        if(authority==host)return host;
    }
    return "";
}
inline DownloadFailure downloadFailure(int code,int tlsCode,std::string_view url,
                                       bool bodyFailed=false,int bodyCode=0) {
    DownloadFailure result;
    result.host=downloadHost(url);
    result.httpStatus=code>=100&&code<=599?code:0;
    if(bodyFailed) {
        result.kind="transfer";result.clientCode=bodyCode<0?bodyCode:0;
    } else if(result.httpStatus) {
        // A real HTTP response takes precedence over an old TLS error.
        result.kind=code==200?"none":"http";
    } else {
        result.clientCode=code<0?code:0;result.tlsCode=tlsCode;
        // Arduino2.0.17 also returns -1 for socket setup/connect/timeouts.
        // That sentinel (or a positive socket result) is not a TLS diagnosis.
        result.kind=tlsCode < -1?"tls":"connection";
    }
    return result;
}
inline std::string downloadFailureMessage(const DownloadFailure &failure) {
    if(std::string_view(failure.kind)=="http")
        return "GitHub returned HTTP "+std::to_string(failure.httpStatus)+".";
    if(std::string_view(failure.kind)=="tls")return "The secure connection to GitHub failed.";
    if(std::string_view(failure.kind)=="transfer")return "The GitHub download was interrupted or incomplete.";
    if(std::string_view(failure.kind)=="connection")return "Could not connect to GitHub.";
    return "";
}
}
