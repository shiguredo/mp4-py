// shiguredo_mp4 の使用バージョンを cargo metadata から解決し、
// コンパイル時の env として下流に埋め込む。
//
// 以前は "../../mp4-rs/Cargo.toml" を include_str! でパースしていたが、
// パスが変わると壊れるため、cargo metadata から依存グラフ経由で取得する。
fn main() {
    let metadata = cargo_metadata::MetadataCommand::new()
        .exec()
        .expect("cargo metadata の実行に失敗した");
    let pkg = metadata
        .packages
        .iter()
        .find(|p| p.name.as_str() == "shiguredo_mp4")
        .expect("shiguredo_mp4 が依存グラフに存在しない");
    println!("cargo::rustc-env=SHIGUREDO_MP4_VERSION={}", pkg.version);
    // Cargo.lock が更新されたら再実行する
    println!("cargo::rerun-if-changed=Cargo.lock");
}
