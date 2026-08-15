---
name: cpp-coding-style
description: "MUST apply when writing, modifying, or reviewing any C or C++ code. MUST trigger on: creating or editing .cpp/.h/.c files, implementing classes or functions, fixing C++ bugs, refactoring C++ code, or any task that produces C/C++ source output. No exceptions."
---
# C++ Coding Style
Follow these C++ coding conventions for consistent, production-grade code.
## Error Handling
- Use return codes instead of exceptions (throw/catch)
- Choose right return value, you can return integer or another value:
	- if you use integer as return value, then 0 is for success, negative values for errors, return error code follow Linux kernel errno code style.
	- if you use bool, then true for success.
	- if you want to use "butil::Status"(when project use brpc as dependency) for return value, then ercode of butil::Status is positive, but still Linux errno(like EINVAL).

## Control Flow
- When if-else nesting becomes deep, use early return to reduce complexity
- Check error conditions first and return early instead of wrapping success logic in nested blocks

## Header Files
- Prevent duplicate or circular include, you need to use like Macro to avoid that, assume HeaderMacro is `_${PROJECT_NAME}_${DIR_NAME}_${SOURCE_FILE_NAME}_H_`
```cpp

#ifndef HeaderMacro
#define HeaderMacro

// your code here

#endif // HeaderMacro

```

## Naming Conventions
- Use snake_case for variable/function names: `my_function_name`, `my_variable_name`
- File names: `my_module.cpp`, `my_header.h`
- Class Name: `class MyClassName`, `class YourClassName`
## Singleton Pattern
- Identify singleton modules and implement appropriately
- If you believe a module only init single times, and a lot of module might use it through a lot of context, then you might need to implement it as Singleton
### example
In a distribute system, there might have a lot of node, each node has different role, like Master/Worker, each node need to communicate each other, so we define a class "NodeTracker" to tracker ip of each role, this is obviously a singleton, and it is often used by various modules in the program, and it can also be decoupled, so we define it as Singleton.
If project dependent on "brpc", then define singleton like this:
```cpp
class NodeTracker {
DISALLOW_COPY_AND_ASSIGN(NodeTracker);
public:
	static NodeTracker* GetInstance() {
        return Singleton<NodeTracker>::get();
    }
    NodeTracker();
    ~NodeTracker();
    
    void method1();
private:
friend struct DefaultSingletonTraits<NodeTracker>;
};

#define g_node_tracker NodeTracker::GetInstance()

// in other module to use it:

g_node_tracker->method1();
```
## Source Code Format
- All C and C++ code and comments, including test code, must use ASCII characters only
- Chinese characters, emoji, and all other non-ASCII characters are forbidden
- All comments must be written in English

## Comments
- **Never** use decorative separator comments made of repeated characters. These are strictly forbidden:
  ```cpp
  // ========
  // --------
  // ********
  // ////////
  ```
- Comments must carry semantic meaning, not visual decoration or section dividers
- Use a blank line to separate logical blocks instead of a banner comment
## Class Member Naming
- Private member variables prefixed with underscore: `_member_variable`

## Private Section Ordering
Split the private section into two blocks: private methods first, private member variables last.
Use two separate `private:` labels to separate them — do not merge them into one block.

### example
```cpp
class Example {
public:
    void DoSomething();

private:
    void HelperMethod();
    int ComputeValue();

private:
    int _count;
    std::string _name;
};
```

## explicit

Only use `explicit` on constructors and conversion operators when implicit conversion would cause genuine ambiguity or hard-to-find bugs. Do not add it by default to every single-argument constructor.

## Copy/Move Control
When disabling copy constructor or copy assignment, prefer `DISALLOW_COPY_AND_ASSIGN(ClassName)` over manual `= delete` declarations. Place it as the first line inside the class body, with no indentation.

## UseCache
- If you like to show How to use it, Ask user first, don't start it without Asking!

## Guidelines
- Prioritize clarity and maintainability
- Follow consistent style throughout the codebase
- Use meaningful variable and function names

## Logging (brpc/glog style)
Use `LOG` and `VLOG` macros for all logging. Never use `printf`, `std::cout`, or `std::cerr` in production code.

```cpp
LOG(INFO)    << "server started on port " << port;
LOG(WARNING) << "retry count exceeded: " << count;
LOG(ERROR)   << "failed to connect: " << endpoint;
VLOG(1)      << "detail trace: " << detail;   // verbose, controlled by --v flag
```

Use `CHECK` macros for invariants that must never be violated:
```cpp
CHECK(ptr != nullptr) << "ptr must not be null";
CHECK_EQ(result, 0)   << "unexpected result: " << result;
CHECK_LT(index, size) << "index out of range";
```
`CHECK` failures are fatal. Use them for programmer errors, not runtime errors.

## Memory Management
- Prefer raw pointers with clear ownership semantics over `shared_ptr` by default
- Use `std::unique_ptr` when a single owner needs RAII cleanup
- Avoid `shared_ptr` unless shared ownership is genuinely required — it hides ownership and adds overhead
- Never use `new`/`delete` directly in business logic; wrap in owning types or factory functions
- Document ownership in comments when passing raw pointers across module boundaries

## Protobuf
When the project uses protobuf:
- Never copy large messages — pass by pointer or reference
- Use `Swap()` to transfer ownership between messages efficiently
- Use `mutable_field()` to get a writable sub-message pointer instead of copying
- Prefer `has_field()` checks before accessing optional fields
- Do not store proto messages as class members if they are large; store them on heap via `unique_ptr`

```cpp
// prefer this
void Process(const MyRequest* req, MyResponse* resp);

// avoid unnecessary copy
MySubMessage* sub = req.mutable_sub();   // no copy
resp->mutable_result()->Swap(&local_result);  // efficient transfer
```

## Configuration Flags (gflags + brpc dynamic flags)

When a parameter is hardcoded but could reasonably be tuned (timeouts, thresholds, buffer sizes, log levels, etc.), extract it as a gflag instead of a magic constant.

**Define with gflags:**
```cpp
DEFINE_int32(rpc_timeout_ms, 1000, "RPC timeout in milliseconds");
DEFINE_bool(enable_prefetch, false, "Enable prefetch optimization");
```

**Dynamic modification at runtime (when project depends on brpc):**

If the parameter can be safely changed while the program is running, register it with `BRPC_VALIDATE_GFLAG` so it becomes modifiable via brpc's `/flags` HTTP endpoint without restarting the process. Place it at file scope right after the `DEFINE_*` line.

```cpp
BRPC_VALIDATE_GFLAG(enable_prefetch, brpc::PassValidate);   // always accepts
BRPC_VALIDATE_GFLAG(rpc_timeout_ms, brpc::PositiveInteger); // must be > 0
```

Only register flags that are genuinely safe to change live — skip flags that are read only once at startup.

## butil Utilities (when project depends on brpc)
Prefer brpc's `butil` types over rolling your own:
- `butil::StringPiece` — non-owning string reference, avoids copies in parsing
- `butil::IOBuf` — efficient non-contiguous byte buffer for network I/O
- `butil::Status` — structured error with code + message (see Error Handling above)
- `butil::Timer` / `butil::MonotonicTime` — for latency measurement
- Avoid `std::string` copies when `butil::StringPiece` suffices
