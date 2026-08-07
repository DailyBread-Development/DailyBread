const menuToggle = document.querySelector("[data-menu-toggle]");
const mobileMenu = document.querySelector("[data-mobile-menu]");

menuToggle?.addEventListener("click", () => {
  const isOpen = !mobileMenu?.classList.contains("hidden");
  mobileMenu?.classList.toggle("hidden", isOpen);
  menuToggle.setAttribute("aria-expanded", String(!isOpen));
});

const userMenu = document.querySelector("[data-user-menu]");
const userMenuToggle = document.querySelector("[data-user-menu-toggle]");

const closeUserMenu = () => {
  userMenu?.classList.remove("is-open");
  userMenuToggle?.setAttribute("aria-expanded", "false");
};

userMenuToggle?.addEventListener("click", () => {
  const isOpen = userMenu?.classList.toggle("is-open");
  userMenuToggle.setAttribute("aria-expanded", String(Boolean(isOpen)));
});

document.addEventListener("click", (event) => {
  if (userMenu && !userMenu.contains(event.target)) closeUserMenu();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeUserMenu();
    userMenuToggle?.focus();
  }
});
