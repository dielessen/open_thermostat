// Test-only executable symbol interposition reaches std::string's shared-
// library allocator. Separate translation unit prevents misleading compiler
// inlining diagnostics about the standard replacement new/delete pair.
#include <new>
#include <cstdlib>
extern bool failConfigAllocation;
void* operator new(size_t bytes) {
    if(failConfigAllocation&&bytes==4097)throw std::bad_alloc();
    if(auto value=std::malloc(bytes?bytes:1))return value;
    throw std::bad_alloc();
}
void operator delete(void* value) noexcept {std::free(value);}
void operator delete(void* value,size_t) noexcept {std::free(value);}
