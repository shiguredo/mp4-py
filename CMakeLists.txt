cmake_minimum_required(VERSION 4.2)
project(mp4-py LANGUAGES CXX)

# プラットフォームチェック
if(NOT APPLE AND NOT UNIX AND NOT WIN32)
  message(FATAL_ERROR "このパッケージは macOS, Linux, Windows のみをサポートしています")
endif()

# Python / nanobind
find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)
find_package(nanobind CONFIG REQUIRED)

include(ExternalProject)

# レイアウト設定
if(DEFINED SKBUILD_PROJECT_DIR)
  set(PROJECT_ROOT "${SKBUILD_PROJECT_DIR}")
else()
  set(PROJECT_ROOT "${CMAKE_CURRENT_SOURCE_DIR}")
endif()

# deps.json から依存情報を読み込む
file(READ "${PROJECT_ROOT}/deps.json" DEPS_JSON)
string(JSON MP4_TAG GET ${DEPS_JSON} "mp4-rust" "tag")
string(JSON MP4_URL GET ${DEPS_JSON} "mp4-rust" "url")

# mp4-rust GitHub Release アーティファクトの設定
set(MP4_BASE_URL "${MP4_URL}/releases/download/${MP4_TAG}")

# プラットフォーム別のアーティファクト名を決定
if(APPLE)
  if(CMAKE_SYSTEM_PROCESSOR MATCHES "arm64|aarch64")
    set(MP4_ARTIFACT "mp4-${MP4_TAG}_macos-26_arm64.tar.gz")
  else()
    message(FATAL_ERROR "macOS x86_64 は mp4-rust リリースでサポートされていません")
  endif()
elseif(WIN32)
  set(MP4_ARTIFACT "mp4-${MP4_TAG}_windows-2025_x86_64.zip")
elseif(UNIX AND NOT APPLE)
  # /etc/os-release から Ubuntu バージョンを検出
  if(NOT EXISTS "/etc/os-release")
    message(FATAL_ERROR "/etc/os-release が見つかりません")
  endif()

  file(READ "/etc/os-release" OS_RELEASE)
  if(OS_RELEASE MATCHES "VERSION_ID=\"([0-9]+)\\.([0-9]+)\"")
    set(OS_VERSION_MAJOR "${CMAKE_MATCH_1}")
    if(OS_VERSION_MAJOR GREATER_EQUAL 24)
      set(UBUNTU_VERSION "24.04")
    else()
      set(UBUNTU_VERSION "22.04")
    endif()
  else()
    message(FATAL_ERROR "Ubuntu バージョンを検出できません")
  endif()

  if(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64")
    set(MP4_ARTIFACT "mp4-${MP4_TAG}_ubuntu-${UBUNTU_VERSION}_arm64.tar.gz")
  else()
    set(MP4_ARTIFACT "mp4-${MP4_TAG}_ubuntu-${UBUNTU_VERSION}_x86_64.tar.gz")
  endif()
endif()

set(MP4_SOURCE_DIR "${PROJECT_ROOT}/_source/mp4-rust")
set(MP4_BUILD_DIR  "${PROJECT_ROOT}/_build/mp4-rust")
set(MP4_LIB_DIR    "${PROJECT_ROOT}/_build/mp4-rust/lib")

# ディレクトリを作成
file(MAKE_DIRECTORY ${MP4_LIB_DIR})

# 静的ライブラリのパス
if(WIN32)
  set(MP4_STATIC_LIB "${MP4_LIB_DIR}/mp4.lib")
else()
  set(MP4_STATIC_LIB "${MP4_LIB_DIR}/libmp4.a")
endif()

# ビルド済みかチェック
if(EXISTS ${MP4_STATIC_LIB})
  message(STATUS "mp4-rust already downloaded: ${MP4_STATIC_LIB}")
  add_custom_target(mp4_rust)
else()
  message(STATUS "Downloading mp4-rust...")
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
                        ${MP4_LIB_DIR}
    BUILD_BYPRODUCTS    ${MP4_STATIC_LIB}
  )
endif()

# nanobind モジュール
nanobind_add_module(mp4_ext
  NB_DOMAIN "mp4"
  FREE_THREADED
  src/mp4_ext.cpp
)

# ビルド順序を保証するため依存関係を追加
add_dependencies(mp4_ext mp4_rust)

# インクルードディレクトリ
target_include_directories(mp4_ext PRIVATE ${MP4_SOURCE_DIR}/include)

# 静的ライブラリをリンク
if(WIN32)
  target_link_libraries(mp4_ext PRIVATE ${MP4_STATIC_LIB} ws2_32 userenv ntdll bcrypt)
else()
  target_link_libraries(mp4_ext PRIVATE ${MP4_STATIC_LIB})
endif()

if(NOT WIN32)
  target_compile_options(mp4_ext PRIVATE -fvisibility=hidden)
endif()

# 型スタブ (.pyi) ファイルの自動生成
nanobind_add_stub(
  mp4_stub
  MODULE mp4_ext
  OUTPUT mp4_ext.pyi
  PYTHON_PATH $<TARGET_FILE_DIR:mp4_ext>
  DEPENDS mp4_ext
  MARKER_FILE py.typed
)

# Wheel に配置するためのインストール先を指定
set(PY_PACKAGE "mp4")
install(TARGETS mp4_ext
  LIBRARY DESTINATION ${PY_PACKAGE}
  RUNTIME DESTINATION ${PY_PACKAGE}
)

# 型スタブファイルとマーカーファイルをインストール
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/mp4_ext.pyi DESTINATION ${PY_PACKAGE})
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/py.typed DESTINATION ${PY_PACKAGE})

# ヘッダファイルもインストール（開発者向け）
install(FILES ${MP4_SOURCE_DIR}/include/mp4.h DESTINATION ${PY_PACKAGE}/include)
