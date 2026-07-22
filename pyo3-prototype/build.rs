// shiguredo_mp4 のバージョンをコンパイル時に取り込む。
// c-api クレートの build.rs と同じ方式で、ルート Cargo.toml から抽出する。
fn main() {
    let toml = include_str!("../../mp4-rs/Cargo.toml");
    let version = toml
        .lines()
        .find_map(|line| {
            let trimmed = line.trim();
            if trimmed.starts_with("version") {
                trimmed
                    .split_once('=')
                    .map(|(_, v)| v.trim().trim_matches('"').to_owned())
            } else {
                None
            }
        })
        .expect("version not found in ../../mp4-rs/Cargo.toml");
    println!("cargo::rustc-env=SHIGUREDO_MP4_VERSION={version}");
    println!("cargo::rerun-if-changed=../../mp4-rs/Cargo.toml");
}
