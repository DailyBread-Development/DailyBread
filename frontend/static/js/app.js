const menuToggle = document.querySelector("[data-menu-toggle]");
const mobileMenu = document.querySelector("[data-mobile-menu]");

const setMobileMenuState = (open) => {
  if (!mobileMenu || !menuToggle) return;
  mobileMenu.classList.toggle("hidden", !open);
  mobileMenu.classList.toggle("is-open", open);
  mobileMenu.setAttribute("aria-hidden", String(!open));
  menuToggle.setAttribute("aria-expanded", String(open));
  menuToggle.setAttribute("aria-label", open ? "Close navigation menu" : "Open navigation menu");
};

setMobileMenuState(false);
menuToggle?.addEventListener("click", () => {
  setMobileMenuState(mobileMenu?.getAttribute("aria-hidden") === "true");
});

mobileMenu?.querySelectorAll("a").forEach((link) => {
  link.addEventListener("click", () => setMobileMenuState(false));
});

const userMenu = document.querySelector("[data-user-menu]");
const userMenuToggle = document.querySelector("[data-user-menu-toggle]");
const mobileUserMenu = document.querySelector(".mobile-user-menu");
const mobileUserMenuToggle = document.querySelector("[data-mobile-user-menu-toggle]");

const closeUserMenu = () => {
  userMenu?.classList.remove("is-open");
  userMenuToggle?.setAttribute("aria-expanded", "false");
};

const userMenuItems = userMenu?.querySelectorAll("[role='menuitem']") || [];

userMenuToggle?.addEventListener("click", () => {
  const isOpen = userMenu?.classList.toggle("is-open");
  userMenuToggle.setAttribute("aria-expanded", String(Boolean(isOpen)));
});

userMenuToggle?.addEventListener("keydown", (event) => {
  if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    userMenu?.classList.add("is-open");
    userMenuToggle.setAttribute("aria-expanded", "true");
    userMenuItems[0]?.focus();
  }
});

mobileUserMenuToggle?.addEventListener("click", () => {
  const isOpen = mobileUserMenu?.classList.toggle("is-open");
  mobileUserMenuToggle.setAttribute("aria-expanded", String(Boolean(isOpen)));
});

userMenuItems.forEach((item, index) => {
  item.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      userMenuItems[(index + 1) % userMenuItems.length]?.focus();
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      userMenuItems[(index - 1 + userMenuItems.length) % userMenuItems.length]?.focus();
    }
    if (event.key === "Home") {
      event.preventDefault();
      userMenuItems[0]?.focus();
    }
    if (event.key === "End") {
      event.preventDefault();
      userMenuItems[userMenuItems.length - 1]?.focus();
    }
    if (event.key === "Escape") {
      closeUserMenu();
      userMenuToggle?.focus();
    }
  });
});

document.addEventListener("click", (event) => {
  if (userMenu && !userMenu.contains(event.target)) closeUserMenu();
  if (mobileUserMenu && !mobileUserMenu.contains(event.target)) {
    mobileUserMenu.classList.remove("is-open");
    mobileUserMenuToggle?.setAttribute("aria-expanded", "false");
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeUserMenu();
    setMobileMenuState(false);
    mobileUserMenu?.classList.remove("is-open");
    mobileUserMenuToggle?.setAttribute("aria-expanded", "false");
    if (document.activeElement === userMenuToggle || userMenu?.contains(document.activeElement)) {
      userMenuToggle?.focus();
    }
  }
});
