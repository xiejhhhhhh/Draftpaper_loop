const translations = {
  en: {
    brandSubtitle: "Local-first research paper loop engine",
    github: "GitHub",
    eyebrow: "Support an auditable research workflow",
    heroTitle: "Make research drafts easier to verify, revise, and reuse.",
    heroText:
      "Draftpaper-loop turns paper writing into a local, traceable loop: retrieve evidence, plan the manuscript, run methods, verify results, repair weak links, and assemble a reviewable LaTeX draft.",
    supportButton: "Support the project",
    quickStart: "Quick start",
    licenseNote: "Donations support maintenance only and do not grant commercial use rights.",
    loopObserve: "Observe",
    loopEvidence: "Evidence",
    loopPlan: "Plan",
    loopMethods: "Methods",
    loopVerify: "Verify",
    loopRepair: "Repair",
    loopLatex: "LaTeX",
    capCitationTitle: "Citation audit loop",
    capCitationText: "Checks whether cited sources support the manuscript claims and routes weak claims into repair.",
    capDisciplineTitle: "Discipline modules",
    capDisciplineText: "Preserves reusable data connectors, method templates, reviewer gates, and project lessons.",
    capLocalTitle: "Local-first state",
    capLocalText: "Keeps project files, manifests, evidence, results, and revision state in a transparent local directory.",
    capReviewTitle: "Reviewer rescue",
    capReviewText: "Turns quality failures into concrete backtracking tasks for data, methods, results, and claims.",
    supportEyebrow: "Tokens for maintenance",
    supportTitle: "If it saves your paper time, you can support the loop.",
    supportText:
      "Support helps maintain documentation, examples, discipline modules, testing, and the local-first workflow. It is appreciated, never required.",
    wechatLabel: "微信支付",
    alipayLabel: "支付宝",
    paypalLabel: "International support",
    floatingLabel: "Support",
    drawerEyebrow: "Support Draftpaper-loop",
    drawerTitle: "Choose a support channel",
    drawerNote: "Support is for maintenance only. Commercial use requires prior written authorization.",
    drawerGithub: "Open GitHub",
    drawerCommercial: "Commercial authorization",
  },
  zh: {
    brandSubtitle: "本地优先的科研论文 loop 引擎",
    github: "GitHub",
    eyebrow: "支持一个可审计的科研工作流",
    heroTitle: "让论文初稿更容易核查、修改和复用。",
    heroText:
      "Draftpaper-loop 将论文写作变成本地、可追溯的 loop：检索证据、规划论文、运行方法、验证结果、修复薄弱环节，并组装可审阅的 LaTeX 初稿。",
    supportButton: "支持项目",
    quickStart: "快速开始",
    licenseNote: "打赏只支持项目维护，不代表商业授权。",
    loopObserve: "观察状态",
    loopEvidence: "证据检索",
    loopPlan: "论文规划",
    loopMethods: "运行方法",
    loopVerify: "结果验证",
    loopRepair: "回退修复",
    loopLatex: "组装 LaTeX",
    capCitationTitle: "引用核查 loop",
    capCitationText: "检查参考文献是否支撑论文论断，并将薄弱论断路由到修复流程。",
    capDisciplineTitle: "学科模块",
    capDisciplineText: "沉淀可复用的数据 connector、方法模板、审稿 gate 和项目经验。",
    capLocalTitle: "本地优先状态",
    capLocalText: "把项目文件、manifest、证据、结果和修订状态保存在透明的本地目录中。",
    capReviewTitle: "审稿式 rescue",
    capReviewText: "把质量失败转化为面向数据、方法、结果和论断的具体回退任务。",
    supportEyebrow: "维护项目的 tokens",
    supportTitle: "如果它节省了你的论文时间，可以支持这个 loop。",
    supportText: "支持将用于维护文档、示例、学科模块、测试和本地优先工作流。感谢支持，但不作强制要求。",
    wechatLabel: "微信支付",
    alipayLabel: "支付宝",
    paypalLabel: "国际支持",
    floatingLabel: "支持",
    drawerEyebrow: "支持 Draftpaper-loop",
    drawerTitle: "选择支持方式",
    drawerNote: "打赏仅用于项目维护。商业使用仍需事先获得书面授权。",
    drawerGithub: "打开 GitHub",
    drawerCommercial: "商业授权",
  },
};

const html = document.documentElement;
const drawer = document.querySelector("[data-support-drawer]");
const lightbox = document.querySelector("[data-qr-lightbox]");
const lightboxImage = document.querySelector("[data-lightbox-image]");
const lightboxLabel = document.querySelector("[data-lightbox-label]");

function setLanguage(language) {
  const lang = language === "zh" ? "zh" : "en";
  html.lang = lang === "zh" ? "zh-CN" : "en";
  localStorage.setItem("draftpaper-support-lang", lang);
  document.querySelector("[data-lang-toggle]").textContent = lang === "zh" ? "English" : "中文";
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const key = node.dataset.i18n;
    if (translations[lang][key]) {
      node.textContent = translations[lang][key];
    }
  });
}

function openDrawer() {
  drawer.classList.add("is-open");
  drawer.setAttribute("aria-hidden", "false");
}

function closeDrawer() {
  drawer.classList.remove("is-open");
  drawer.setAttribute("aria-hidden", "true");
}

function openLightbox(src, label) {
  lightboxImage.src = src;
  lightboxImage.alt = label;
  lightboxLabel.textContent = label;
  lightbox.classList.add("is-open");
  lightbox.setAttribute("aria-hidden", "false");
}

function closeLightbox() {
  lightbox.classList.remove("is-open");
  lightbox.setAttribute("aria-hidden", "true");
}

document.querySelector("[data-lang-toggle]").addEventListener("click", () => {
  setLanguage(html.lang === "zh-CN" ? "en" : "zh");
});

document.querySelectorAll("[data-open-support]").forEach((button) => {
  button.addEventListener("click", openDrawer);
});

document.querySelectorAll("[data-close-support]").forEach((button) => {
  button.addEventListener("click", closeDrawer);
});

document.querySelectorAll("[data-focus-qr]").forEach((button) => {
  button.addEventListener("click", () => {
    openLightbox(button.dataset.focusQr, button.dataset.focusLabel);
  });
});

document.querySelector("[data-close-lightbox]").addEventListener("click", closeLightbox);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeLightbox();
    closeDrawer();
  }
});

const savedLanguage = localStorage.getItem("draftpaper-support-lang");
const browserLanguage = navigator.language && navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en";
setLanguage(savedLanguage || browserLanguage);
