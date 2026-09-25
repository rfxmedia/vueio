cmake_minimum_required(VERSION 3.24)
project(VueioModelPreview LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
include(FetchContent)
set(USE_TESTS OFF CACHE BOOL "" FORCE)
set(USE_BINARIES OFF CACHE BOOL "" FORCE)
set(USE_EXAMPLES OFF CACHE BOOL "" FORCE)
set(USE_HDF5 OFF CACHE BOOL "" FORCE)
set(ALEMBIC_SHARED_LIBS OFF CACHE BOOL "" FORCE)
FetchContent_Declare(alembic
  URL https://codeload.github.com/alembic/alembic/tar.gz/refs/tags/1.8.12
  URL_HASH SHA256=b6d916c40446e8c502c84273092ab3d98f3f7f6094f8a2b8203d23e2f1d2a4a0)
FetchContent_Declare(earcut
  URL https://codeload.github.com/mapbox/earcut.hpp/tar.gz/refs/tags/v2.2.4
  URL_HASH SHA256=fcfa6a47a52d4c94dc960bdb747f17e077609235517b0bb5ce8097d6b747695a)
FetchContent_MakeAvailable(alembic)
# earcut is header-only. Do not configure its benchmark/test project.
FetchContent_GetProperties(earcut)
if(NOT earcut_POPULATED)
  FetchContent_Populate(earcut)
endif()
find_package(ZLIB REQUIRED)
add_executable(vueio-model-preview main.cpp)
target_include_directories(vueio-model-preview PRIVATE ${earcut_SOURCE_DIR}/include)
target_link_libraries(vueio-model-preview PRIVATE Alembic ZLIB::ZLIB)
install(TARGETS vueio-model-preview RUNTIME DESTINATION bin COMPONENT decoder)
install(FILES ${alembic_SOURCE_DIR}/LICENSE.txt DESTINATION share/doc/vueio-model-preview RENAME ALEMBIC_LICENSE.txt COMPONENT decoder)
install(FILES ${earcut_SOURCE_DIR}/LICENSE DESTINATION share/doc/vueio-model-preview RENAME EARCUT_LICENSE.txt COMPONENT decoder)
