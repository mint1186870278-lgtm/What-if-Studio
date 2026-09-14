import "./landing.css";

/**
 * The public-facing archive that introduces What-if Studio.
 *
 * This is intentionally local data: the archive is a discovery surface, not
 * a catalogue service.  A selected title is handed to the existing studio
 * form through the small `onEnterStudio` callback, so the creative workflow
 * remains the single source of truth for uploads, discussion and rendering.
 */
const FEATURED_WORKS = [
  {
    id: "phoenix",
    title: "哈利·波特与凤凰社",
    originalTitle: "Harry Potter and the Order of the Phoenix",
    year: "2007",
    type: "电影",
    genre: "奇幻 / 成长",
    cover: "phoenix",
    synopsis: "哈利在魔法部的否认与乌姆里奇的压迫中长大，和伙伴们秘密组成邓布利多军，准备面对伏地魔卷土重来的真相。",
    ending: "神秘事务司之战后，小天狼星跌入帷幕后离世。哈利失去重要的家人，也终于确认战争已经开始。",
    prompt: "小天狼星在神秘事务司被救下，最终和哈利拥抱和解。",
    tags: ["改写命运", "家人", "温情"],
  },
  {
    id: "titanic",
    title: "泰坦尼克号",
    originalTitle: "Titanic",
    year: "1997",
    type: "电影",
    genre: "爱情 / 灾难",
    cover: "titanic",
    synopsis: "来自不同阶层的杰克与露丝在首航的巨轮上相遇，在短暂的自由里共同看见另一种人生。",
    ending: "船沉入北大西洋。露丝活下来，杰克留在冰冷的海水里，成为她一生不曾忘记的夏天。",
    prompt: "让救生门有足够空间，两个人一起活下来，并在多年后重返海面。",
    tags: ["如果当时", "爱情", "重逢"],
  },
  {
    id: "interstellar",
    title: "星际穿越",
    originalTitle: "Interstellar",
    year: "2014",
    type: "电影",
    genre: "科幻 / 亲情",
    cover: "interstellar",
    synopsis: "地球濒临崩溃，库珀离开女儿踏上穿越虫洞的远征，在时间与引力的缝隙里寻找人类的未来。",
    ending: "库珀终于与老年的墨菲重逢，却又踏上寻找布兰德的旅程；父女相见，仍然来不及停留。",
    prompt: "库珀留在空间站陪伴墨菲，把最后一次远行交给下一代。",
    tags: ["另一条时间线", "父女", "宇宙"],
  },
  {
    id: "game-of-thrones",
    title: "权力的游戏",
    originalTitle: "Game of Thrones",
    year: "2011—2019",
    type: "剧集",
    genre: "史诗 / 权谋",
    cover: "thrones",
    synopsis: "七大王国在冰与火之间争夺王座，家族、誓言与野心把每个人都推向无法回头的选择。",
    ending: "丹妮莉丝死于铁王座前，王国改由议会选王；北境独立，史塔克兄妹各自走向新的道路。",
    prompt: "让权力交接先经过公开审判，给丹妮莉丝一次真正的选择与赎罪。",
    tags: ["重写终局", "权力", "赎罪"],
  },
  {
    id: "dark-knight",
    title: "蝙蝠侠：黑暗骑士",
    originalTitle: "The Dark Knight",
    year: "2008",
    type: "电影",
    genre: "犯罪 / 英雄",
    cover: "dark-knight",
    synopsis: "哥谭迎来一位以混乱为乐的敌人。蝙蝠侠、戈登与哈维·丹特试图守住城市的信念，却被迫付出沉重代价。",
    ending: "蝙蝠侠承担双面人的罪名，成为被追捕的黑暗骑士，让城市保留对哈维的希望。",
    prompt: "让哥谭听见完整真相，蝙蝠侠与戈登一起承担城市的选择。",
    tags: ["英雄选择", "城市", "真相"],
  },
  {
    id: "lord-of-the-rings",
    title: "指环王：王者无敌",
    originalTitle: "The Lord of the Rings: The Return of the King",
    year: "2003",
    type: "电影",
    genre: "奇幻 / 史诗",
    cover: "rings",
    synopsis: "中土世界迎来最后一战。弗罗多与山姆走进末日火山，阿拉贡则带领自由人民守住黎明前的战场。",
    ending: "魔戒毁灭，战争结束。弗罗多带着无法愈合的伤离开中土世界，朋友们在夏尔迎来迟到的和平。",
    prompt: "让弗罗多留在夏尔，朋友们一起找到修复创伤的方法。",
    tags: ["归乡", "创伤修复", "伙伴"],
  },
  {
    id: "spirited-away",
    title: "千与千寻",
    originalTitle: "Spirited Away",
    year: "2001",
    type: "电影",
    genre: "动画 / 奇幻",
    cover: "spirited-away",
    synopsis: "千寻误入神灵的世界，在汤屋里学会工作、记住名字，也在一次次告别中找到自己的勇气。",
    ending: "千寻救回父母并离开隧道。她没有回头，却把那段经历带回了现实，像一盏尚未熄灭的灯。",
    prompt: "让千寻长大后再次回到汤屋，和白龙一起寻找被遗忘的名字。",
    tags: ["再见面", "成长", "记忆"],
  },
  {
    id: "wandering-earth",
    title: "流浪地球",
    originalTitle: "The Wandering Earth",
    year: "2019",
    type: "电影",
    genre: "科幻 / 灾难",
    cover: "earth",
    synopsis: "太阳即将毁灭，人类把地球推离故乡。刘培强、刘启与无数普通人，在绝境里把希望交给彼此。",
    ending: "点燃木星的危机暂时解除，地球继续驶向新的恒星；人类的家园仍在路上。",
    prompt: "让空间站与地面建立双向救援，父子在新航程开始前真正告别。",
    tags: ["另一种牺牲", "家园", "远航"],
  },
];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function cardTemplate(work, copy = "") {
  return `
    <button class="archive-card archive-card--${escapeHtml(work.cover)}" type="button"
      data-work-id="${escapeHtml(work.id)}" data-copy="${escapeHtml(copy)}"
      aria-label="查看 ${escapeHtml(work.title)} 的剧情与结尾">
      <span class="archive-card__grain" aria-hidden="true"></span>
      <span class="archive-card__topline"><span>${escapeHtml(work.type)}</span><span>${escapeHtml(work.year)}</span></span>
      <span class="archive-card__title">${escapeHtml(work.title)}</span>
      <span class="archive-card__original">${escapeHtml(work.originalTitle)}</span>
      <span class="archive-card__genre">${escapeHtml(work.genre)}</span>
      <span class="archive-card__footer"><span>打开档案</span><span class="archive-card__mark">↗</span></span>
    </button>
  `;
}

function isStudioRoute() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  const query = new URLSearchParams(window.location.search);
  return path === "/studio" || path.startsWith("/studio/") || query.has("project") || query.get("view") === "studio";
}

function setDialogOpen(dialog, open) {
  if (!dialog) return;
  if (open) {
    if (typeof dialog.showModal === "function") {
      if (!dialog.open) dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }
    dialog.classList.add("is-open");
  } else {
    if (typeof dialog.close === "function" && dialog.open) dialog.close();
    dialog.removeAttribute("open");
    dialog.classList.remove("is-open");
  }
}

/** Mount the archive and wire its transition into the existing studio. */
export function mountLanding({ workspace, onEnterStudio, onListProjects, onOpenProject } = {}) {
  const app = document.querySelector("#app");
  if (!app || !workspace) return null;
  if (app.__whatIfLanding?.root?.isConnected) return app.__whatIfLanding;

  const landing = document.createElement("main");
  landing.className = "landing-page";
  landing.id = "landing-page";
  landing.setAttribute("aria-labelledby", "landing-title");
  landing.innerHTML = `
    <header class="landing-nav">
      <a class="landing-brand" href="/" aria-label="What-if Studio 首页">
        <span class="landing-brand__sigil" aria-hidden="true">W</span>
        <span><strong>WHAT-IF</strong><small>STUDIO / PARALLEL CUTS</small></span>
      </a>
      <div class="landing-nav__right">
        <a class="landing-nav__link" href="#archive">作品档案</a>
        <button class="landing-nav__open" type="button" data-action="open-project">打开已有工程</button>
        <button class="landing-nav__studio" type="button">进入创作工作台 <span aria-hidden="true">↗</span></button>
      </div>
    </header>

    <section class="landing-hero" aria-labelledby="landing-title">
      <div class="landing-hero__backdrop" aria-hidden="true">
        <span class="landing-hero__halo"></span>
        <span class="landing-hero__orbit landing-hero__orbit--one"></span>
        <span class="landing-hero__orbit landing-hero__orbit--two"></span>
        <span class="landing-hero__frame landing-hero__frame--left">CUT / 01</span>
        <span class="landing-hero__frame landing-hero__frame--right">ARCHIVE / 2026</span>
      </div>
      <div class="landing-hero__copy">
        <p class="landing-eyebrow"><span class="landing-eyebrow__line"></span> A CREATIVE ENGINE FOR UNFINISHED ENDINGS</p>
        <h1 id="landing-title">有些结局，<br /><em>值得再拍一次。</em></h1>
        <p class="landing-hero__lede">What-if Studio 把一句“如果当时……”交给一支虚拟剧组。让故事保留原作的重量，也给遗憾一条新的时间线。</p>
        <div class="landing-hero__actions">
          <a class="landing-primary-cta" href="#archive">浏览作品档案 <span aria-hidden="true">↓</span></a>
          <button class="landing-secondary-cta" type="button" data-action="enter-studio">直接开始二创 <span aria-hidden="true">↗</span></button>
        </div>
      </div>
      <div class="landing-hero__annotation" aria-hidden="true">
        <span class="landing-hero__annotation-label">THE MOMENT<br />BEFORE THE CUT</span>
        <span class="landing-hero__annotation-rule"></span>
        <span class="landing-hero__annotation-note">保留情绪 · 重写选择 · 交给剧组</span>
      </div>
      <a class="landing-scroll-cue" href="#archive"><span class="landing-scroll-cue__mouse" aria-hidden="true"></span><span>向下滚动，进入档案</span></a>
    </section>

    <section class="landing-intro" aria-labelledby="intro-title">
      <div class="landing-section-index">01 / WHY WHAT-IF</div>
      <div class="landing-intro__content">
        <p class="landing-eyebrow">NOT A SUMMARY. A SECOND TAKE.</p>
        <h2 id="intro-title">从“意难平”开始，<br /><span>把观看变成共同创作。</span></h2>
        <p>你选择一部熟悉的作品，先看清它留下的那道伤口，再决定要不要动笔。叙事、视觉、声音与素材导演会围绕同一个 Creative Brief 讨论，直到一个新的结局值得被看见。</p>
        <div class="landing-crew-strip" aria-label="虚拟剧组成员">
          <div class="landing-crew-strip__portraits">
            <img src="/mock/avatars/director-yates.png" alt="大卫·叶茨" loading="lazy" />
            <img src="/mock/avatars/director-columbus.png" alt="克里斯·哥伦布" loading="lazy" />
            <img src="/mock/avatars/director-jackson.png" alt="彼得·杰克逊" loading="lazy" />
            <img src="/mock/avatars/director-burton.png" alt="蒂姆·伯顿" loading="lazy" />
          </div>
          <span>四种视角 · 一个共享简报</span>
        </div>
        <div class="landing-principles" role="list">
          <article role="listitem"><span>01</span><strong>先理解</strong><small>剧情与原作结尾被完整呈现，选择从知情开始。</small></article>
          <article role="listitem"><span>02</span><strong>再分歧</strong><small>多位导演提出不同方向，在关键分叉处向你提问。</small></article>
          <article role="listitem"><span>03</span><strong>后重拍</strong><small>确认你的选择，进入工作台，生成属于你的平行版本。</small></article>
        </div>
      </div>
      <div class="landing-intro__stamp" aria-hidden="true"><span>KEEP<br />THE<br />FEELING</span><i></i></div>
    </section>

    <section class="landing-archive" id="archive" aria-labelledby="archive-title">
      <div class="landing-archive__head">
        <div>
          <div class="landing-section-index">02 / THE ARCHIVE</div>
          <h2 id="archive-title">你想改写哪一个<br /><em>结尾？</em></h2>
        </div>
        <div class="landing-archive__controls">
          <p>横向浏览 · 点击打开档案</p>
          <div>
            <button class="archive-arrow" type="button" data-direction="prev" aria-label="上一部作品">←</button>
            <button class="archive-arrow" type="button" data-direction="next" aria-label="下一部作品">→</button>
          </div>
        </div>
      </div>
      <div class="archive-viewport" tabindex="0" aria-label="经典影视作品横向档案">
        <div class="archive-track"></div>
      </div>
      <div class="landing-archive__hint"><span class="landing-archive__hint-line"></span><span>每一个结尾，都是一扇尚未关闭的门</span><span class="landing-archive__hint-line"></span></div>
    </section>

    <footer class="landing-footer">
      <div><span class="landing-footer__mark">W</span><span>WHAT-IF STUDIO</span></div>
      <p>为那些仍然留在心里的故事，保留一次平行剪辑。</p>
      <button type="button" data-action="enter-studio">进入创作工作台 <span aria-hidden="true">↗</span></button>
    </footer>

    <dialog class="archive-dialog" aria-labelledby="archive-dialog-title">
      <button class="archive-dialog__close" type="button" data-dialog-close aria-label="关闭作品档案">×</button>
      <div class="archive-dialog__visual" aria-hidden="true"><span class="archive-dialog__visual-index"></span><span class="archive-dialog__visual-title"></span></div>
      <div class="archive-dialog__body">
        <div class="archive-dialog__meta"><span class="archive-dialog__type"></span><span>·</span><span class="archive-dialog__year"></span><span>·</span><span class="archive-dialog__genre"></span></div>
        <h2 id="archive-dialog-title"></h2>
        <p class="archive-dialog__original"></p>
        <div class="archive-dialog__section"><span>剧情简介</span><p class="archive-dialog__synopsis"></p></div>
        <div class="archive-dialog__section archive-dialog__section--ending"><span>原作结尾 · SPOILER</span><p class="archive-dialog__ending"></p></div>
        <div class="archive-dialog__prompt"><span>如果你想改写：</span><p class="archive-dialog__rewrite"></p></div>
        <div class="archive-dialog__tags"></div>
        <p class="archive-dialog__decision">要不要把这个结尾，交给剧组重拍一次？</p>
        <div class="archive-dialog__actions"><button type="button" class="archive-dialog__later" data-dialog-close>先继续浏览</button><button type="button" class="archive-dialog__enter" data-dialog-enter>进入二创 <span aria-hidden="true">↗</span></button></div>
      </div>
    </dialog>

    <dialog class="project-dialog" aria-labelledby="project-dialog-title">
      <button class="archive-dialog__close" type="button" data-project-dialog-close aria-label="关闭工程列表">×</button>
      <div class="project-dialog__body">
        <div class="landing-section-index">YOUR WORKSPACE</div>
        <h2 id="project-dialog-title">打开已有工程</h2>
        <p class="project-dialog__hint">继续上次的讨论，或从列表中选择一个工程。</p>
        <div class="project-dialog__list" role="list" aria-live="polite"></div>
      </div>
    </dialog>
  `;
  app.insertBefore(landing, workspace);

  const track = landing.querySelector(".archive-track");
  const viewport = landing.querySelector(".archive-viewport");
  const dialog = landing.querySelector(".archive-dialog");
  const dialogTitle = landing.querySelector("#archive-dialog-title");
  const dialogOriginal = landing.querySelector(".archive-dialog__original");
  const dialogType = landing.querySelector(".archive-dialog__type");
  const dialogYear = landing.querySelector(".archive-dialog__year");
  const dialogGenre = landing.querySelector(".archive-dialog__genre");
  const dialogSynopsis = landing.querySelector(".archive-dialog__synopsis");
  const dialogEnding = landing.querySelector(".archive-dialog__ending");
  const dialogRewrite = landing.querySelector(".archive-dialog__rewrite");
  const dialogTags = landing.querySelector(".archive-dialog__tags");
  const dialogVisualIndex = landing.querySelector(".archive-dialog__visual-index");
  const dialogVisualTitle = landing.querySelector(".archive-dialog__visual-title");
  const projectDialog = landing.querySelector(".project-dialog");
  const projectDialogList = landing.querySelector(".project-dialog__list");
  let selectedWork = null;
  let transitionTimer = null;

  // Duplicate the finite archive for a seamless CSS marquee.  Each duplicate
  // carries the same data id, so keyboard/click activation behaves identically.
  track.innerHTML = `${FEATURED_WORKS.map((work) => cardTemplate(work, "a")).join("")}${FEATURED_WORKS.map((work) => cardTemplate(work, "b")).join("")}`;

  function openWork(workId) {
    const work = FEATURED_WORKS.find((item) => item.id === workId);
    if (!work) return;
    selectedWork = work;
    dialogTitle.textContent = work.title;
    dialogOriginal.textContent = work.originalTitle;
    dialogType.textContent = work.type;
    dialogYear.textContent = work.year;
    dialogGenre.textContent = work.genre;
    dialogSynopsis.textContent = work.synopsis;
    dialogEnding.textContent = work.ending;
    dialogRewrite.textContent = work.prompt;
    dialogVisualIndex.textContent = `ARCHIVE / ${String(FEATURED_WORKS.indexOf(work) + 1).padStart(2, "0")}`;
    dialogVisualTitle.textContent = work.title;
    dialogTags.innerHTML = work.tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("");
    dialog.className = `archive-dialog archive-dialog--${work.cover}`;
    setDialogOpen(dialog, true);
  }

  function enterStudio(selection = null) {
    const work = selection || selectedWork;
    setDialogOpen(dialog, false);
    landing.classList.add("is-leaving");
    if (transitionTimer) window.clearTimeout(transitionTimer);
    transitionTimer = window.setTimeout(() => {
      if (!isStudioRoute()) return;
      landing.classList.add("is-hidden");
      workspace.classList.remove("is-hidden");
      workspace.removeAttribute("hidden");
      document.body.classList.remove("landing-mode");
    }, 180);
    const target = new URL(window.location.href);
    target.pathname = "/studio";
    target.hash = "";
    if (work) target.searchParams.delete("project");
    window.history.pushState({}, "", `${target.pathname}${target.search}`);
    const payload = work ? {
      workTitle: work.title,
      endingDirection: work.prompt,
      workId: work.id,
    } : {};
    if (typeof onEnterStudio === "function") {
      onEnterStudio(payload);
    } else if (work) {
      // Keep the module useful when the existing studio is embedded without a
      // router callback.  The form remains the source of truth for creation.
      const titleInput = document.querySelector("#work-title");
      const promptInput = document.querySelector("#ending-direction");
      if (titleInput) titleInput.value = payload.workTitle;
      if (promptInput) promptInput.value = payload.endingDirection;
    }
    window.dispatchEvent(new CustomEvent("whatif:archive-selection", { detail: payload }));
  }

  async function openExistingProjects() {
    setDialogOpen(projectDialog, true);
    projectDialogList.innerHTML = `<p class="project-dialog__loading">正在加载工程…</p>`;
    if (typeof onListProjects !== "function") {
      projectDialogList.innerHTML = `<p class="project-dialog__empty">当前没有可打开的工程。</p>`;
      return;
    }
    try {
      const projects = await onListProjects();
      if (!Array.isArray(projects) || projects.length === 0) {
        projectDialogList.innerHTML = `<p class="project-dialog__empty">还没有工程，先从作品档案开始一次二创。</p>`;
        return;
      }
      projectDialogList.innerHTML = projects.map((project) => `
        <button class="project-dialog__item" type="button" data-project-id="${escapeHtml(project.id)}">
          <span class="project-dialog__item-main"><strong>${escapeHtml(project.name || "未命名工程")}</strong><small>${escapeHtml(project.prompt || "暂无需求")}</small></span>
          <span class="project-dialog__item-meta">${escapeHtml(project.discussion_status || "idle")} ↗</span>
        </button>
      `).join("");
      projectDialogList.querySelectorAll("[data-project-id]").forEach((button) => {
        button.addEventListener("click", async () => {
          const project = projects.find((item) => String(item.id) === button.dataset.projectId);
          if (!project) return;
          if (typeof onOpenProject === "function") await onOpenProject(project);
          setDialogOpen(projectDialog, false);
          syncRoute();
        });
      });
    } catch (error) {
      projectDialogList.innerHTML = `<p class="project-dialog__empty">工程加载失败：${escapeHtml(error?.message || "请稍后重试")}</p>`;
    }
  }

  function leaveStudioForLanding() {
    if (transitionTimer) {
      window.clearTimeout(transitionTimer);
      transitionTimer = null;
    }
    landing.classList.remove("is-hidden", "is-leaving");
    workspace.classList.add("is-hidden");
    workspace.setAttribute("hidden", "");
    document.body.classList.add("landing-mode");
    setDialogOpen(dialog, false);
  }

  landing.querySelectorAll(".archive-card").forEach((card) => {
    card.addEventListener("click", () => openWork(card.dataset.workId));
  });
  landing.querySelectorAll("[data-dialog-close]").forEach((button) => {
    button.addEventListener("click", () => setDialogOpen(dialog, false));
  });
  landing.querySelector("[data-dialog-enter]")?.addEventListener("click", () => enterStudio());
  landing.querySelectorAll('[data-action="enter-studio"], .landing-nav__studio').forEach((button) => {
    button.addEventListener("click", () => enterStudio());
  });
  landing.querySelector('[data-action="open-project"]')?.addEventListener("click", openExistingProjects);
  landing.querySelectorAll("[data-project-dialog-close]").forEach((button) => {
    button.addEventListener("click", () => setDialogOpen(projectDialog, false));
  });
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) setDialogOpen(dialog, false);
  });
  dialog.addEventListener("cancel", () => setDialogOpen(dialog, false));
  projectDialog?.addEventListener("click", (event) => {
    if (event.target === projectDialog) setDialogOpen(projectDialog, false);
  });
  projectDialog?.addEventListener("cancel", () => setDialogOpen(projectDialog, false));

  // Keep the marquee useful for people who prefer direct manipulation.  On
  // touch-sized screens CSS turns off the animation and this becomes a normal
  // horizontal scroller; desktop users can also use the arrow controls.
  landing.querySelectorAll(".archive-arrow").forEach((button) => {
    button.addEventListener("click", () => {
      const direction = button.dataset.direction === "prev" ? -1 : 1;
      const amount = Math.max(260, viewport.clientWidth * 0.62);
      viewport.scrollBy({ left: direction * amount, behavior: "smooth" });
    });
  });
  viewport.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const amount = Math.max(260, viewport.clientWidth * 0.62);
    viewport.scrollBy({ left: event.key === "ArrowLeft" ? -amount : amount, behavior: "smooth" });
  });
  viewport.addEventListener("wheel", (event) => {
    if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
    if (viewport.scrollWidth <= viewport.clientWidth) return;
    event.preventDefault();
    viewport.scrollLeft += event.deltaY;
  }, { passive: false });

  function syncRoute() {
    if (isStudioRoute()) {
      landing.classList.add("is-hidden");
      workspace.classList.remove("is-hidden");
      workspace.removeAttribute("hidden");
      document.body.classList.remove("landing-mode");
    } else {
      leaveStudioForLanding();
    }
  }
  window.addEventListener("popstate", syncRoute);
  syncRoute();

  const handle = {
    enterStudio,
    openExistingProjects,
    openWork,
    works: FEATURED_WORKS,
    root: landing,
  };
  app.__whatIfLanding = handle;
  return handle;
}

export { FEATURED_WORKS };
