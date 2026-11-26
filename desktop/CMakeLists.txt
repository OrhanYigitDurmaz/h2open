# h2open desktop app: C++23 and Qt 6 Widgets.
#
#   cmake --preset dev && cmake --build --preset dev && ctest --preset dev
cmake_minimum_required(VERSION 3.28)
project(h2open-desktop VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
# No C++ modules: skip the module scan (and its GCC-only flags).
set(CMAKE_CXX_SCAN_FOR_MODULES OFF)
# clang-tidy reads the compile commands.
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

find_package(Qt6 6.8 REQUIRED COMPONENTS Widgets Network Test)
qt_standard_project_setup(REQUIRES 6.8)

# Strict warnings, as errors, for our code only (Qt's headers are system
# headers, so their warnings stay out).
add_library(h2open_options INTERFACE)
if(MSVC)
    target_compile_options(h2open_options INTERFACE /W4 /WX /permissive-)
else()
    target_compile_options(h2open_options INTERFACE
        -Wall -Wextra -Wpedantic -Werror
        -Wconversion -Wsign-conversion -Wshadow -Wold-style-cast
        -Wnon-virtual-dtor -Woverloaded-virtual -Wnull-dereference
        -Wimplicit-fallthrough -Wcast-qual -Wformat=2)
endif()
target_compile_definitions(h2open_options INTERFACE
    # Every string must say its encoding (u"…"_s), and nothing deprecated.
    QT_NO_CAST_FROM_ASCII
    QT_NO_CAST_TO_ASCII
    QT_NO_URL_CAST_FROM_STRING
    QT_NO_NARROWING_CONVERSIONS_IN_CONNECT
    QT_DISABLE_DEPRECATED_UP_TO=0x060800)

# Talking to the server, kept apart from the UI so tests can link it alone.
add_library(h2open_api STATIC src/api.cpp src/api.h)
target_include_directories(h2open_api PUBLIC src)
target_link_libraries(h2open_api PUBLIC Qt6::Core Qt6::Network PRIVATE h2open_options)

qt_add_executable(h2open-desktop WIN32
    src/main.cpp
    src/desktopapp.cpp src/desktopapp.h
    src/dimlabel.cpp src/dimlabel.h
    src/loginwindow.cpp src/loginwindow.h
    src/mainwindow.cpp src/mainwindow.h
    src/gallery.cpp src/gallery.h)
target_link_libraries(h2open-desktop PRIVATE h2open_api Qt6::Widgets h2open_options)

enable_testing()
qt_add_executable(test_api tests/test_api.cpp)
target_link_libraries(test_api PRIVATE h2open_api Qt6::Test h2open_options)
add_test(NAME api COMMAND test_api)
# No display needed for the tests.
set_tests_properties(api PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
