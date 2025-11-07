cmake_minimum_required(VERSION 3.15)
project(mp4-py)

include(ExternalProject)

# mp4-rust GitHub Release アーティファクトの設定
set(MP4_VERSION "2025.3.0" CACHE STRING "mp4-rust のバージョン")
set(MP4_BASE_URL "https://github.com/shiguredo/mp4-rust/releases/download/${MP4_VERSION}" CACHE STRING "mp4-rust リリースの基本 URL")

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

# wheel パッケージにはヘッダとライブラリをコピー
install(FILES ${MP4_SOURCE_DIR}/include/mp4.h
  DESTINATION mp4_py/include
)

# 動的ライブラリを wheel パッケージにインストール
if(APPLE)
  install(FILES ${MP4_LIB_INSTALL_DIR}/libmp4.dylib
    DESTINATION mp4_py/lib
  )
elseif(UNIX AND NOT APPLE)
  install(FILES ${MP4_LIB_INSTALL_DIR}/libmp4.so
    DESTINATION mp4_py/lib
  )
endif()

