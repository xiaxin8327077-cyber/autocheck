export function bindSearch({ input, listen, runtime, channel = "rule-search", onSearch }) {
  listen(input, "input", () => {
    runtime.debounce(channel, () => onSearch(input.value.trim()), 300);
  });
  listen(input, "keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    runtime.clearDebounce(channel);
    onSearch(input.value.trim());
  });
}
