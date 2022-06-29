set(LLVM_LINK_COMPONENTS Option Support)

add_clang_tool(binder
  binder.cpp
  binder.hpp
  context.cpp
  class.cpp
  config.cpp
  enum.cpp
  function.cpp
  type.cpp
  util.cpp
  fmt/format.cc
  fmt/os.cc
  )

clang_target_link_libraries(binder
	PRIVATE
	clangTooling
	clangBasic
	clangAST
	clangASTMatchers
	clangFrontend)

install(TARGETS binder
        RUNTIME DESTINATION bin
        COMPONENT clang-extras)
