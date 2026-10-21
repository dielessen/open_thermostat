// Finite decoder/evaluator probe; no hardware, transport or installation grants.
#include "control/BoundedJson.h"
#include "control/ScheduleDocument.h"
#include <iostream>
#include <string>

int main() {
    using namespace heating::control;
    std::string line;
    while(std::getline(std::cin,line)) {
        auto root=parseControlJson(line);
        if(!root)return 2;
        auto get=[&](const char* key){return cJSON_GetObjectItemCaseSensitive(root.get(),key);};
        UtcSchedule schedule;
        const bool accepted=configureScheduleDocument(schedule,get("schedule"),cJSON_IsTrue(get("allow_packed")));
        ControlJson result(cJSON_CreateObject(),cJSON_Delete);
        cJSON_AddBoolToObject(result.get(),"accepted",accepted);
        auto rows=cJSON_AddArrayToObject(result.get(),"targets");
        const auto times=get("times");
        if(!cJSON_IsArray(times))return 3;
        for(auto at=times->child;at;at=at->next) {
            if(!cJSON_IsNumber(at))return 4;
            auto target=schedule.target(static_cast<int64_t>(at->valuedouble),cJSON_IsTrue(get("clock_valid")));
            auto row=cJSON_CreateObject();cJSON_AddItemToArray(rows,row);
            cJSON_AddNumberToObject(row,"state",static_cast<int>(target.state));
            cJSON_AddItemToObject(row,"target",target.temperatureCentiC?cJSON_CreateNumber(*target.temperatureCentiC):cJSON_CreateNull());
            cJSON_AddItemToObject(row,"next_at",target.next?cJSON_CreateNumber(target.next->atUtc):cJSON_CreateNull());
            cJSON_AddItemToObject(row,"next_target",target.next?cJSON_CreateNumber(target.next->temperatureCentiC):cJSON_CreateNull());
        }
        auto text=cJSON_PrintUnformatted(result.get());if(!text)return 5;
        std::cout<<text<<std::endl;cJSON_free(text);
    }
}
