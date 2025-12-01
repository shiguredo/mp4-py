cmake_minimum_required(VERSION 4.1)
project(mp4_py LANGUAGES CXX)

include(ExternalProject)
find_package(Python 3.12 COMPONENTS Interpreter Development.Module REQUIRED)

# nanobind を検索
execute_process(
  COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir
  OUTPUT_STRIP_TRAILING_WHITESPACE OUTPUT_VARIABLE nanobind_ROOT
)
find_package(nanobind CONFIG REQUIRED)

# deps.json からバージョン情報を読み込む
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/deps.json" DEPS_JSON)
string(JSON MP4_VERSION GET ${DEPS_JSON} "mp4-rust" "version")
string(JSON MP4_REPOSITORY GET ${DEPS_JSON} "mp4-rust" "repository")

# mp4-rust GitHub Release アーティファクトの設定
set(MP4_BASE_URL "${MP4_REPOSITORY}/releases/download/${MP4_VERSION}")

# プラットフォーム別のアーティファクト名を決定
if(APPLE)
  if(CMAKE_SYSTEM_PROCESSOR MATCHES "arm64|aarch64")
    set(MP4_ARTIFACT "mp4-${MP4_VERSION}_macos-26_arm64.tar.gz")
  else()
    message(FATAL_ERROR "macOS x86_64 は mp4-rust リリースでサポートされていません")
  endif()
elseif(UNIX AND NOT APPLE)
  if(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64")
    set(MP4_ARTIFACT "mp4-${MP4_VERSION}_ubuntu-24.04_arm64.tar.gz")
  else()
    set(MP4_ARTIFACT "mp4-${MP4_VERSION}_ubuntu-24.04_x86_64.tar.gz")
  endif()
elseif(WIN32)
  message(FATAL_ERROR "Windows はまだ mp4-rust リリースでサポートされていません")
else()
  message(FATAL_ERROR "サポートされていないプラットフォームです")
endif()

# レイアウト設定
if(DEFINED SKBUILD_PROJECT_DIR)
  set(PROJECT_ROOT "${SKBUILD_PROJECT_DIR}")
else()
  set(PROJECT_ROOT "${CMAKE_CURRENT_SOURCE_DIR}")
endif()

set(MP4_SOURCE_DIR "${PROJECT_ROOT}/_source/mp4-rust")
set(MP4_BUILD_DIR  "${PROJECT_ROOT}/_build/mp4-rust")
set(MP4_LIB_INSTALL_DIR "${PROJECT_ROOT}/_build/mp4-rust/lib")
set(MP4_INCLUDE_DIR "${MP4_SOURCE_DIR}/include")

# ディレクトリを作成
file(MAKE_DIRECTORY ${MP4_LIB_INSTALL_DIR})

# mp4-rust ライブラリをダウンロードして抽出
ExternalProject_Add(mp4_rust
  URL                 ${MP4_BASE_URL}/${MP4_ARTIFACT}
  SOURCE_DIR          ${MP4_SOURCE_DIR}
  BINARY_DIR          ${MP4_BUILD_DIR}
  STAMP_DIR           ${MP4_BUILD_DIR}/stamp
  TMP_DIR             ${MP4_BUILD_DIR}/tmp
  UPDATE_COMMAND      ""
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE
  CONFIGURE_COMMAND   ""
  BUILD_COMMAND       ""
  # ライブラリを _build/mp4-rust/lib にコピー
  INSTALL_COMMAND     ${CMAKE_COMMAND} -E copy_directory
                      ${MP4_SOURCE_DIR}/lib
                      ${MP4_LIB_INSTALL_DIR}
  BUILD_BYPRODUCTS
    ${MP4_LIB_INSTALL_DIR}/libmp4.so
    ${MP4_LIB_INSTALL_DIR}/libmp4.dylib
)

# nanobind モジュールを作成
nanobind_add_module(_mp4
  NB_DOMAIN "mp4"
  src/mp4_ext.cpp
)

add_dependencies(_mp4 mp4_rust)

# インクルードディレクトリを設定
target_include_directories(_mp4 PRIVATE ${MP4_INCLUDE_DIR})

# mp4 ライブラリをリンク
if(APPLE)
  set(MP4_LIB "${MP4_LIB_INSTALL_DIR}/libmp4.dylib")
elseif(UNIX AND NOT APPLE)
  set(MP4_LIB "${MP4_LIB_INSTALL_DIR}/libmp4.so")
endif()

target_link_libraries(_mp4 PRIVATE ${MP4_LIB})

# RPATH 設定
if(APPLE)
  # libmp4.dylib の install_name を変更
  add_custom_command(TARGET _mp4 PRE_LINK
    COMMAND install_name_tool -id "@rpath/libmp4.dylib" "${MP4_LIB}" || true
    VERBATIM
  )
  set_target_properties(_mp4 PROPERTIES
    BUILD_RPATH "${MP4_LIB_INSTALL_DIR}"
    INSTALL_RPATH "@loader_path/lib"
  )
elseif(UNIX AND NOT APPLE)
  set_target_properties(_mp4 PROPERTIES
    BUILD_RPATH "${MP4_LIB_INSTALL_DIR}"
    INSTALL_RPATH "$ORIGIN/lib"
  )
endif()

# 型スタブを自動生成
nanobind_add_stub(
  mp4_stub
  MODULE _mp4
  OUTPUT __init__.pyi
  PYTHON_PATH $<TARGET_FILE_DIR:_mp4>
  DEPENDS _mp4
  MARKER_FILE py.typed
)

# nanobind モジュールを wheel パッケージにインストール
install(TARGETS _mp4 LIBRARY DESTINATION mp4)

# 型スタブファイルをインストール
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/__init__.pyi DESTINATION mp4)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/py.typed DESTINATION mp4)

# 動的ライブラリを wheel パッケージにインストール
if(APPLE)
  install(FILES ${MP4_LIB_INSTALL_DIR}/libmp4.dylib
    DESTINATION mp4/lib
  )
elseif(UNIX AND NOT APPLE)
  install(FILES ${MP4_LIB_INSTALL_DIR}/libmp4.so
    DESTINATION mp4/lib
  )
endif()
