// 独立模块既有资源协议支持 JSON；分片保证每个原稿字体资源小于 5 MiB。
// 字体使用模块私有名称，不影响宿主页面和执行弹窗。
let loading = null;
export function loadResultFonts() {
  if (!globalThis.FontFace || !globalThis.document?.fonts) return Promise.resolve();
  if (loading) return loading;
  loading = Promise.all(["400", "500", "600"].map(async weight => {
    const parts = await Promise.all(["a", "b"].map(async part => {
      const response = await fetch(new URL(`../fonts/Noto_Sans_SC-${weight}-${part}.json`, import.meta.url), { credentials: "same-origin", cache: "force-cache" });
      if (!response.ok) throw new Error("结果页本地字体未加载");
      return (await response.json()).data;
    }));
    const binary = atob(parts.join(""));
    const bytes = Uint8Array.from(binary, char => char.charCodeAt(0));
    const font = new FontFace("DVResultsNoto_Sans_SC", bytes, { weight, style: "normal", display: "swap" });
    await font.load(); document.fonts.add(font);
  })).catch(error => { loading = null; throw error; });
  return loading;
}
