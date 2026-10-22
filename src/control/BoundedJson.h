#pragma once
#include <cJSON.h>
#include <cmath>
#include <cstring>
#include <memory>
#include <string>
#include <string_view>

namespace heating::control {
using ControlJson = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;

// Restricted v1 CONTROL JSON, not a general JSON replacement. Human labels stay
// in HA: wire identifiers/literals are printable ASCII without escapes. Enforce
// budgets before allocating a cJSON tree (including its recursive parser stack).
inline ControlJson parseControlJson(std::string_view bytes,bool deviceSettings=false) {
    const auto reject=[] { return ControlJson(nullptr,cJSON_Delete); };
    constexpr std::size_t maxBytes=8192, maxNodes=512, maxDepth=8;
    const std::size_t maxStringBytes=deviceSettings?512:64;
    if (bytes.empty() || bytes.size()>maxBytes) return reject();
    if(deviceSettings && bytes.find("\\u0000")!=std::string_view::npos) return reject();
    const auto whitespace=[](char c) { return c==' ' || c=='\t' || c=='\r' || c=='\n'; };
    const auto digit=[](char c) { return c>='0' && c<='9'; };
    std::size_t depth=0, nodes=0;
    for(std::size_t i=0;i<bytes.size();) {
        const unsigned char c=bytes[i];
        if(whitespace(c) || c==',' || c==':') { ++i; continue; }
        if(c=='{' || c=='[') {
            if(++depth>maxDepth || ++nodes>maxNodes) return reject();
            ++i; continue;
        }
        if(c=='}' || c==']') { if(!depth) return reject(); --depth; ++i; continue; }
        if(c=='"') {
            const auto begin=++i;
            while(i<bytes.size() && bytes[i]!='"') {
                if(static_cast<unsigned char>(bytes[i])<32 ||
                   (!deviceSettings && (static_cast<unsigned char>(bytes[i])>126||bytes[i]=='\\')) || i-begin>=maxStringBytes) return reject();
                if(deviceSettings && bytes[i]=='\\') { if(++i==bytes.size()||i-begin>=maxStringBytes) return reject(); }
                ++i;
            }
            if(i==bytes.size() || ++nodes>maxNodes) return reject();
            ++i; continue;
        }
        if(c=='-' || digit(c)) {
            if(c=='-' && ++i==bytes.size()) return reject();
            if(bytes[i]=='0') { ++i; if(i<bytes.size() && digit(bytes[i])) return reject(); }
            else {
                if(!digit(bytes[i]) || bytes[i]=='0') return reject();
                do { ++i; } while(i<bytes.size() && digit(bytes[i]));
            }
            if(i<bytes.size() && bytes[i]=='.') {
                ++i; const auto start=i;
                while(i<bytes.size() && digit(bytes[i])) ++i;
                if(i==start) return reject();
            }
            if(i<bytes.size() && (bytes[i]=='e' || bytes[i]=='E')) {
                ++i;
                if(i<bytes.size() && (bytes[i]=='+' || bytes[i]=='-')) ++i;
                const auto start=i;
                while(i<bytes.size() && digit(bytes[i])) ++i;
                if(i==start) return reject();
            }
            if(i<bytes.size() && !whitespace(bytes[i]) && bytes[i]!=',' && bytes[i]!=']' && bytes[i]!='}') return reject();
            if(++nodes>maxNodes) return reject();
            continue;
        }
        bool keyword=false;
        for(auto text:{std::string_view("true"),std::string_view("false"),std::string_view("null")}) {
            if(bytes.substr(i,text.size())==text) { i+=text.size(); keyword=true; break; }
        }
        if(!keyword || ++nodes>maxNodes) return reject();
    }
    if(depth) return reject();
    // Exactly one complete document; embedded NUL/escaped-key aliases have
    // already been rejected. cJSON supplies the actual syntax/type parser.
    const std::string owned(bytes);
    ControlJson root(cJSON_ParseWithLengthOpts(owned.c_str(),owned.size()+1,nullptr,true),cJSON_Delete);
    if(!root) return reject();
    const auto uniqueAndFinite=[](auto &&self,const cJSON *node)->bool {
        if(cJSON_IsNumber(node) && !std::isfinite(node->valuedouble)) return false;
        for(auto child=node->child;child;child=child->next) {
            if(cJSON_IsObject(node)) {
                if(!child->string) return false;
                for(auto prior=node->child;prior!=child;prior=prior->next)
                    if(!std::strcmp(prior->string,child->string)) return false;
            }
            if(!self(self,child)) return false;
        }
        return true;
    };
    if(!uniqueAndFinite(uniqueAndFinite,root.get())) return reject();
    return root;
}
}
