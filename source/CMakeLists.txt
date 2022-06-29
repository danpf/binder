set(LLVM_LINK_COMPONENTS Option Support)

add_clang_tool(binder
  main.cpp
  binder.cpp
  class.cpp
  config.cpp
  context.cpp
  enum.cpp
  function.cpp
  options.cpp
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
