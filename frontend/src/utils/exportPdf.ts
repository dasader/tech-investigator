export function printCurrentView(): void {
  document.body.classList.add("printing-data");
  const cleanup = () => {
    document.body.classList.remove("printing-data");
    window.removeEventListener("afterprint", cleanup);
  };
  window.addEventListener("afterprint", cleanup);
  window.print();
}
