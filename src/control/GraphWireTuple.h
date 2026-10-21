#pragma once
#include "GraphShadowValidation.h"

namespace heating::control {
// Explicit API2 transport form: same canonical envelope with ONE extra root
// mapping object. No extra nesting, no separate mapping commit, no HA entity/
// service strings. Only encode after the SAME full shared semantic validator.
// Decoder only separates syntax/integrity; owner still MUST admit+apply core.
struct GraphWireParts {std::string message,mapping;};
inline void graphTupleEnvelope(const cJSON* o,bool mapping) {
    using namespace heating::graph_test;
    if(mapping)object(o,{"api","controller_id","boot_id","epoch","adapter_id","adapter_session_id","grant_id",
        "grant_sequence","config_revision","binding_id","sequence","expected_revision","config_digest","config","mapping"});
    else object(o,{"api","controller_id","boot_id","epoch","adapter_id","adapter_session_id","grant_id",
        "grant_sequence","config_revision","binding_id","sequence","expected_revision","config_digest","config"});
    need(integer(get(o,"api"),2,2)==2,"unsupported_schema");
    need(cJSON_IsObject(get(o,"config")),"schema");
}
inline GraphWireParts decodeGraphTuple(std::string_view bytes,const heating::graph_test::Hash& hash) {
    using namespace heating::graph_test;
    auto root=parse(bytes);graphTupleEnvelope(root.get(),true);
    Json mapping(cJSON_DetachItemFromObjectCaseSensitive(root.get(),"mapping"),cJSON_Delete);
    need(bool(mapping)&&cJSON_IsObject(mapping.get()),"mapping_conflict");
    GraphWireParts parts{print(root.get()),print(mapping.get())};
    const auto digest=hash?hash(parts.mapping):std::string();
    need(hex(digest),"hash_fault");
    literal(get(get(root.get(),"config"),"mapping_digest"),digest.c_str(),"mapping_conflict");
    return parts;
}
inline std::string encodeGraphTuple(std::string_view message,std::string_view mapping,
        const heating::graph_test::Context& context,const heating::graph_test::Hash& hash) {
    using namespace heating::graph_test;
    const auto valid=validate(message,mapping,context,hash);
    need(valid.code=="valid_shadow_candidate","wire_tuple_invalid");
    auto inner=parse(message);auto map=parse(mapping);graphTupleEnvelope(inner.get(),false);
    // Exact validated inner schema ends in sequence. Transfer owned subtrees
    // instead of retaining a duplicated third tree. RAII keeps ownership until
    // cJSON confirms transfer, including failure of the key allocation.
    Json sequence(cJSON_DetachItemFromObjectCaseSensitive(inner.get(),"sequence"),cJSON_Delete);
    need(bool(sequence),"schema");
    need(cJSON_AddItemToObject(inner.get(),"mapping",map.get()),"allocation");map.release();
    need(cJSON_AddItemToObject(inner.get(),"sequence",sequence.get()),"allocation");sequence.release();
    const auto raw=print(inner.get());inner.reset();
    // Enforce TOTAL transport byte/node/depth/string bounds and canonical order,
    // not only each component's individual ceiling. Do not retain another tree.
    auto checked=parse(raw);(void)checked;return raw;
}
}
