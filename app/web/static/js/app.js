document.addEventListener("DOMContentLoaded", function () {
  const tg = window.Telegram ? window.Telegram.WebApp : null;
  if (tg) {
    try {
      tg.ready();
      tg.expand();
      document.body.classList.add("telegram-theme");
    } catch (e) {
      console.warn("Telegram WebApp init error", e);
    }
  }

  let currentData = null;

  function formatMoney(amount) {
    const num = Math.round(Number(amount) || 0);
    return num.toLocaleString("ru-RU") + " ₽";
  }

  function formatDate(dateStr) {
    if (!dateStr) return "";
    const d = new Date(dateStr);
    const day = String(d.getDate()).padStart(2, "0");
    const month = String(d.getMonth() + 1).padStart(2, "0");
    return `${day}.${month}`;
  }

  // Tab Navigation
  const navItems = document.querySelectorAll(".nav-item");
  const tabPages = document.querySelectorAll(".tab-page");

  navItems.forEach(item => {
    item.addEventListener("click", function () {
      const targetTab = this.getAttribute("data-tab");
      navItems.forEach(n => {
        n.classList.remove("active");
        n.style.color = "var(--text-muted)";
      });
      this.classList.add("active");
      this.style.color = "var(--accent-blue)";

      tabPages.forEach(p => p.style.display = "none");
      const activePage = document.getElementById("tab-" + targetTab);
      if (activePage) activePage.style.display = "block";
    });
  });

  let currentScope = "family";

  // Budget Scope Switcher (Family vs Personal)
  const scopeBtnFamily = document.getElementById("scope-btn-family");
  const scopeBtnPersonal = document.getElementById("scope-btn-personal");

  if (scopeBtnFamily && scopeBtnPersonal) {
    scopeBtnFamily.addEventListener("click", () => {
      if (currentScope === "family") return;
      currentScope = "family";
      scopeBtnFamily.classList.add("active");
      scopeBtnFamily.style.background = "var(--accent-blue)";
      scopeBtnFamily.style.color = "white";
      scopeBtnPersonal.classList.remove("active");
      scopeBtnPersonal.style.background = "transparent";
      scopeBtnPersonal.style.color = "var(--text-muted)";
      loadSummary();
      loadTrendsChart();
      loadOperationsTabList();
    });

    scopeBtnPersonal.addEventListener("click", () => {
      if (currentScope === "personal") return;
      currentScope = "personal";
      scopeBtnPersonal.classList.add("active");
      scopeBtnPersonal.style.background = "var(--accent-blue)";
      scopeBtnPersonal.style.color = "white";
      scopeBtnFamily.classList.remove("active");
      scopeBtnFamily.style.background = "transparent";
      scopeBtnFamily.style.color = "var(--text-muted)";
      loadSummary();
      loadTrendsChart();
      loadOperationsTabList();
    });
  }

  function getUid() {
    let uid = "";
    if (tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.id) {
      uid = tg.initDataUnsafe.user.id;
    }
    if (!uid) {
      const _urlParams = new URLSearchParams(window.location.search);
      uid = _urlParams.get("uid") || "";
    }
    if (!uid) {
      try { uid = localStorage.getItem("user_uid") || ""; } catch(e) {}
    }
    if (uid) {
      try { localStorage.setItem("user_uid", String(uid)); } catch(e) {}
    }
    return uid;
  }

  function getAuthHeaders() {
    const headers = {};
    if (tg && tg.initData) {
      headers["telegram-web-app-init-data"] = tg.initData;
    } else {
      const urlParams = new URLSearchParams(window.location.search);
      const hashStr = window.location.hash.startsWith("#") ? window.location.hash.substring(1) : window.location.hash;
      const hashParams = new URLSearchParams(hashStr);
      const initDataStr = urlParams.get("tgWebAppData") || urlParams.get("initData") || hashParams.get("tgWebAppData") || hashParams.get("initData");
      if (initDataStr) {
        headers["telegram-web-app-init-data"] = initDataStr;
      }
    }
    return headers;
  }

  function apiUrl(path) {
    const uid = getUid();
    const sep = path.includes("?") ? "&" : "?";
    return uid ? `${path}${sep}uid=${uid}` : path;
  }

  async function loadSummary() {
    try {
      const headers = getAuthHeaders();

      const res = await fetch(apiUrl(`/api/summary?scope=${currentScope}`), { headers });
      if (!res.ok) {
        document.getElementById("content").innerHTML = `<div class="loading">Ошибка загрузки данных (${res.status})</div>`;
        return;
      }

      currentData = await res.json();
      renderApp(currentData);
      populateAccountInputs(currentData);
    } catch (err) {
      console.error(err);
      document.getElementById("content").innerHTML = `<div class="loading">Не удалось связаться с сервером</div>`;
    }
  }

  function renderApp(data) {
    // Balances
    const totalCap = Number(data.total_capital) || Number(data.balance) || 1;
    document.getElementById("total-capital").textContent = formatMoney(data.total_capital || data.balance);
    document.getElementById("total-balance").textContent = formatMoney(data.balance);

    document.getElementById("month-income").textContent = "+" + formatMoney(data.income_month);
    document.getElementById("month-expense").textContent = "-" + formatMoney(data.expense_month);
    document.getElementById("free-cash-flow").textContent = formatMoney(data.free_cash_flow);
    document.getElementById("savings-rate").textContent = (data.savings_rate || 0).toFixed(1) + "%";

    // Financial Runway
    const runwayVal = document.getElementById("runway-value");
    if (data.financial_runway_months >= 99) {
      runwayVal.textContent = "Безгранично 🎉";
    } else {
      runwayVal.textContent = `${data.financial_runway_months.toFixed(1)} мес. трат`;
      runwayVal.style.color = data.financial_runway_months < 3 ? "var(--accent-red)" : "var(--accent-green)";
    }

    // Asset Allocation Bar
    if (data.accounts && data.accounts.length > 0) {
      const mainAcc = data.accounts.find(a => a.type === "main");
      const savAcc = data.accounts.find(a => a.type === "savings" && a.enabled);
      const depAcc = data.accounts.find(a => a.type === "deposit" && a.enabled);

      const mainBal = mainAcc ? Math.max(0, Number(mainAcc.balance)) : 0;
      const savBal = savAcc ? Math.max(0, Number(savAcc.balance)) : 0;
      const depBal = depAcc ? Math.max(0, Number(depAcc.balance)) : 0;

      const mainPct = Math.round((mainBal / totalCap) * 100);
      const savPct = Math.round((savBal / totalCap) * 100);
      const depPct = Math.round((depBal / totalCap) * 100);

      document.getElementById("alloc-main").style.width = mainPct + "%";
      document.getElementById("alloc-savings").style.width = savPct + "%";
      document.getElementById("alloc-deposit").style.width = depPct + "%";
    }

    // Accounts breakdown
    const accContainer = document.getElementById("accounts-list");
    accContainer.innerHTML = "";
    if (data.accounts && data.accounts.length > 0) {
      const activeAccounts = data.accounts.filter(a => a.enabled);
      if (activeAccounts.length > 0) {
        activeAccounts.forEach(acc => {
          const item = document.createElement("div");
          item.className = "cat-item";
          let subText = "";
          if (acc.type === "savings") {
            subText = acc.apy > 0 ? `Ставка ${acc.apy}% APY • ~+${formatMoney(acc.monthly_interest)}/мес` : "Без процентов";
          } else if (acc.type === "deposit") {
            subText = acc.apy > 0 ? `Ставка ${acc.apy}% APY на ${acc.months} мес • На выходе ~${formatMoney(acc.projected_total)}` : "Без процента";
          } else {
            subText = "Карта / Наличные";
          }

          item.innerHTML = `
            <div class="cat-info">
              <span class="cat-name">${acc.name}</span>
              <span class="cat-meta">${subText}</span>
            </div>
            <span class="tx-amount" style="color: var(--text-main);">${formatMoney(acc.balance)}</span>
          `;
          accContainer.appendChild(item);
        });

        if (data.total_passive_income_monthly > 0) {
          const passiveItem = document.createElement("div");
          passiveItem.className = "cat-meta";
          passiveItem.style.padding = "6px 8px";
          passiveItem.style.color = "var(--accent-green)";
          passiveItem.style.fontWeight = "600";
          passiveItem.textContent = `💸 Пассивный доход по процентам: ~+${formatMoney(data.total_passive_income_monthly)}/мес`;
          accContainer.appendChild(passiveItem);
        }
      } else {
        accContainer.innerHTML = `<div class="cat-meta" style="padding: 10px;">Нет активных счетов</div>`;
      }
    }

    // Category Budgets
    const budgetsContainer = document.getElementById("budgets-list");
    budgetsContainer.innerHTML = "";
    if (data.category_budgets && data.category_budgets.length > 0) {
      data.category_budgets.forEach(b => {
        const item = document.createElement("div");
        item.className = "goal-card";
        let statusColor = "var(--accent-green)";
        if (b.percentage >= 100) statusColor = "var(--accent-red)";
        else if (b.percentage >= 80) statusColor = "#f59e0b";

        item.innerHTML = `
          <div class="goal-header">
            <span>🏷 ${b.category}</span>
            <span>${formatMoney(b.spent)} / ${formatMoney(b.limit)}</span>
          </div>
          <div class="goal-progress-bar">
            <div class="goal-progress-fill" style="width: ${Math.min(100, b.percentage)}%; background: ${statusColor}"></div>
          </div>
          <div class="goal-meta">
            <span>Потрачено: ${b.percentage.toFixed(0)}%</span>
            <span style="color: ${statusColor}">${b.percentage >= 100 ? '⚠️ Превышен' : 'В норме'}</span>
          </div>
        `;
        budgetsContainer.appendChild(item);
      });
    } else {
      budgetsContainer.innerHTML = `<div class="cat-meta" style="padding: 10px;">Бюджеты не настроены (перейдите во вкладку «🏦 Счета»)</div>`;
    }

    // Top Categories
    const catContainer = document.getElementById("top-categories");
    catContainer.innerHTML = "";
    if (data.top_expense_categories && data.top_expense_categories.length > 0) {
      data.top_expense_categories.forEach(cat => {
        const item = document.createElement("div");
        item.className = "cat-item";
        item.innerHTML = `
          <div class="cat-info">
            <span class="cat-name">${cat.category}</span>
            <span class="cat-meta">${cat.percentage.toFixed(1)}% от трат за месяц</span>
          </div>
          <span class="tx-amount expense">-${formatMoney(cat.amount)}</span>
        `;
        catContainer.appendChild(item);
      });
    } else {
      catContainer.innerHTML = `<div class="cat-meta" style="padding: 10px;">Нет расходов за текущий месяц</div>`;
    }

    // Goals
    const goalsContainer = document.getElementById("goals-list");
    goalsContainer.innerHTML = "";
    if (data.active_goals && data.active_goals.length > 0) {
      data.active_goals.forEach(goal => {
        const item = document.createElement("div");
        item.className = "goal-card";
        item.style.position = "relative";
        item.innerHTML = `
          <div class="goal-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <span style="font-weight: 700;">🎯 ${goal.title}</span>
            <span style="font-weight: 800;">${formatMoney(goal.current_amount)} / ${formatMoney(goal.target_amount)}</span>
          </div>
          <div class="goal-progress-bar" style="margin-bottom: 8px;">
            <div class="goal-progress-fill" style="width: ${goal.progress_percentage}%"></div>
          </div>
          <div class="goal-meta" style="display: flex; justify-content: space-between; align-items: center; font-size: 0.8rem; color: var(--text-muted);">
            <span>Прогресс: <strong>${goal.progress_percentage.toFixed(0)}%</strong> • ${goal.status === 'done' ? 'Достигнута 🎉' : 'В процессе'}</span>
            <div style="display: flex; gap: 6px;">
              <button class="goal-contribute-btn" data-id="${goal.id}" data-title="${goal.title}" style="padding: 4px 8px; border-radius: 6px; border: none; background: rgba(59, 130, 246, 0.2); color: var(--accent-blue); font-size: 0.75rem; font-weight: 700; cursor: pointer;">➕ Внести</button>
              <button class="goal-delete-btn" data-id="${goal.id}" style="padding: 4px 8px; border-radius: 6px; border: none; background: rgba(239, 68, 68, 0.15); color: var(--accent-red); font-size: 0.75rem; cursor: pointer;">🗑</button>
            </div>
          </div>
        `;
        goalsContainer.appendChild(item);
      });

      // Attach event listeners for goals
      document.querySelectorAll(".goal-contribute-btn").forEach(btn => {
        btn.addEventListener("click", async function () {
          const goalId = this.getAttribute("data-id");
          const title = this.getAttribute("data-title");
          const inputVal = prompt(`Сумма взноса в цель «${title}» (₽):`);
          const amount = parseFloat(inputVal);
          if (!amount || amount <= 0) return;

          try {
            const h = { "Content-Type": "application/json" };
            if (tg && tg.initData) h["telegram-web-app-init-data"] = tg.initData;

            const res = await fetch(`/api/goals/${goalId}/contribute`, {
              method: "POST",
              headers: h,
              body: JSON.stringify({ amount })
            });

            if (res.ok) {
              alert(`✅ Взнос ${formatMoney(amount)} в цель «${title}» сохранён!`);
              loadSummary();
            } else {
              alert("Ошибка сохранения взноса");
            }
          } catch (e) { console.error(e); }
        });
      });

      document.querySelectorAll(".goal-delete-btn").forEach(btn => {
        btn.addEventListener("click", async function () {
          const goalId = this.getAttribute("data-id");
          if (!confirm("Удалить эту цель?")) return;

          try {
            const h = {};
            if (tg && tg.initData) h["telegram-web-app-init-data"] = tg.initData;

            const res = await fetch(`/api/goals/${goalId}`, { method: "DELETE", headers: h });
            if (res.ok) loadSummary();
          } catch (e) { console.error(e); }
        });
      });

    } else {
      goalsContainer.innerHTML = `<div class="cat-meta" style="padding: 10px;">Нет активных целей</div>`;
    }

    // Recent Transactions
    const txContainer = document.getElementById("recent-transactions");
    txContainer.innerHTML = "";
    if (data.recent_transactions && data.recent_transactions.length > 0) {
      data.recent_transactions.forEach(tx => {
        const item = document.createElement("div");
        item.className = "tx-item";
        const sign = tx.type === "income" ? "+" : (tx.type === "expense" ? "-" : "");
        const categoryStr = tx.category ? ` • ${tx.category}` : "";

        item.innerHTML = `
          <div class="tx-info">
            <span class="tx-title">${tx.note || tx.category || "Операция"}</span>
            <span class="tx-sub">${formatDate(tx.date)}${categoryStr}</span>
          </div>
          <span class="tx-amount ${tx.type}">${sign}${formatMoney(tx.amount)}</span>
        `;
        txContainer.appendChild(item);
      });
    } else {
      txContainer.innerHTML = `<div class="cat-meta" style="padding: 10px;">Нет операций</div>`;
    }
  }

  function populateAccountInputs(data) {
    if (data && data.accounts) {
      const mainAcc = data.accounts.find(a => a.type === "main");
      const savAcc = data.accounts.find(a => a.type === "savings");
      const depAcc = data.accounts.find(a => a.type === "deposit");

      if (mainAcc) document.getElementById("acc-main-bal").value = mainAcc.balance;
      if (savAcc) {
        document.getElementById("acc-sav-bal").value = savAcc.balance;
        document.getElementById("acc-sav-apy").value = savAcc.apy || 0;
        document.getElementById("acc-sav-enabled").checked = savAcc.enabled;
      }
      if (depAcc) {
        document.getElementById("acc-dep-bal").value = depAcc.balance;
        document.getElementById("acc-dep-apy").value = depAcc.apy || 0;
        document.getElementById("acc-dep-months").value = depAcc.months || 12;
        document.getElementById("acc-dep-enabled").checked = depAcc.enabled;
      }
    }
  }

  // Operation Type Toggle
  let selectedOpType = "expense";
  const opTypeBtns = document.querySelectorAll(".op-type-btn");
  opTypeBtns.forEach(btn => {
    btn.addEventListener("click", function () {
      opTypeBtns.forEach(b => {
        b.style.background = "transparent";
        b.style.color = "var(--text-main)";
        b.classList.remove("active");
      });
      this.classList.add("active");
      selectedOpType = this.getAttribute("data-type");

      const transferSelect = document.getElementById("transfer-accounts-select");
      const catContainer = document.getElementById("category-select-container");

      if (selectedOpType === "transfer") {
        this.style.background = "var(--accent-blue)";
        this.style.color = "white";
        transferSelect.style.display = "block";
        catContainer.style.display = "none";
      } else if (selectedOpType === "income") {
        this.style.background = "var(--accent-green)";
        this.style.color = "white";
        transferSelect.style.display = "none";
        catContainer.style.display = "block";
      } else {
        this.style.background = "var(--accent-red)";
        this.style.color = "white";
        transferSelect.style.display = "none";
        catContainer.style.display = "block";
      }
    });
  });

  const opDateEl = document.getElementById("op-date");
  if (opDateEl && !opDateEl.value) {
    opDateEl.value = new Date().toISOString().split("T")[0];
  }

  // Create Operation
  const submitOpBtn = document.getElementById("submit-op-btn");
  if (submitOpBtn) {
    submitOpBtn.addEventListener("click", async function () {
      const amount = Number(document.getElementById("op-amount").value);
      if (!amount || amount <= 0) {
        alert("Пожалуйста, введите корректную сумму");
        return;
      }

      const payload = {
        type: selectedOpType,
        amount: amount,
        category: selectedOpType === "transfer" ? "Переводы" : document.getElementById("op-category").value,
        note: document.getElementById("op-note").value,
        target_account: document.getElementById("op-target-account").value,
        date: document.getElementById("op-date")?.value || undefined
      };

      try {
        const headers = { "Content-Type": "application/json" };
        if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

        const res = await fetch("/api/operations", {
          method: "POST",
          headers: headers,
          body: JSON.stringify(payload)
        });

        if (res.ok) {
          document.getElementById("op-amount").value = "";
          document.getElementById("op-note").value = "";
          alert("✅ Операция успешно сохранена!");
          loadSummary();
          loadOperationsTabList();
        } else {
          alert("Ошибка при сохранении операции");
        }
      } catch (err) {
        console.error(err);
        alert("Ошибка связи с сервером");
      }
    });
  }

  // QR Code File Upload
  const uploadQrBtn = document.getElementById("upload-qr-btn");
  const qrFileInput = document.getElementById("qr-file-input");
  const qrStatus = document.getElementById("qr-scan-status");

  if (uploadQrBtn && qrFileInput) {
    uploadQrBtn.addEventListener("click", () => qrFileInput.click());
    qrFileInput.addEventListener("change", async function () {
      if (!this.files || !this.files[0]) return;
      const file = this.files[0];
      qrStatus.textContent = "⏳ Сканирование QR-кода...";

      const formData = new FormData();
      formData.append("file", file);

      try {
        const headers = {};
        if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

        const res = await fetch("/api/scan_qr", {
          method: "POST",
          headers: headers,
          body: formData
        });

        const data = await res.json();
        if (data.success) {
          qrStatus.innerHTML = `✅ <strong style="color: var(--accent-green)">Считан чек на ${data.amount} ₽!</strong>`;
          document.getElementById("op-amount").value = data.amount;
          document.getElementById("op-note").value = data.note;
        } else {
          qrStatus.textContent = "❌ " + (data.message || "Не удалось найти QR-код чека на снимке");
        }
      } catch (err) {
        console.error(err);
        qrStatus.textContent = "❌ Ошибка отправки фото";
      }
    });
  }

  // Save Accounts in Tab 3
  const saveAccTabBtn = document.getElementById("save-accounts-tab-btn");
  if (saveAccTabBtn) {
    saveAccTabBtn.addEventListener("click", async function () {
      const payload = {
        main_balance: Number(document.getElementById("acc-main-bal").value) || 0,
        savings_balance: Number(document.getElementById("acc-sav-bal").value) || 0,
        savings_apy: Number(document.getElementById("acc-sav-apy").value) || 0,
        savings_enabled: Boolean(document.getElementById("acc-sav-enabled").checked),
        deposit_balance: Number(document.getElementById("acc-dep-bal").value) || 0,
        deposit_apy: Number(document.getElementById("acc-dep-apy").value) || 0,
        deposit_months: Number(document.getElementById("acc-dep-months").value) || 12,
        deposit_enabled: Boolean(document.getElementById("acc-dep-enabled").checked)
      };

      try {
        const headers = { "Content-Type": "application/json" };
        if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

        const res = await fetch("/api/accounts", {
          method: "POST",
          headers: headers,
          body: JSON.stringify(payload)
        });

        if (res.ok) {
          alert("✅ Параметры счетов сохранены!");
          loadSummary();
        } else {
          alert("Ошибка сохранения счетов");
        }
      } catch (err) {
        console.error(err);
        alert("Не удалось сохранить счета");
      }
    });
  }

  // Save Category Budget Limit
  const saveBudgetBtn = document.getElementById("save-budget-btn");
  if (saveBudgetBtn) {
    saveBudgetBtn.addEventListener("click", async function () {
      const cat = document.getElementById("budget-cat-select").value;
      const limit = Number(document.getElementById("budget-limit-input").value);
      if (!limit || limit <= 0) {
        alert("Введите сумму лимита больше 0");
        return;
      }

      try {
        const headers = { "Content-Type": "application/json" };
        if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

        const res = await fetch("/api/budgets", {
          method: "POST",
          headers: headers,
          body: JSON.stringify({ category: cat, limit: limit })
        });

        if (res.ok) {
          alert(`✅ Лимит для «${cat}» сохранен!`);
          document.getElementById("budget-limit-input").value = "";
          loadSummary();
        } else {
          alert("Ошибка сохранения лимита");
        }
      } catch (err) {
        console.error(err);
      }
    });
  }

  // AI Chat Assistant
  const chatFeed = document.getElementById("ai-chat-feed");
  const chatInput = document.getElementById("ai-chat-input");
  const sendAiBtn = document.getElementById("send-ai-btn");
  const chipBtns = document.querySelectorAll(".ai-chip-btn");

  async function sendAiQuestion(questionText) {
    if (!questionText.trim()) return;

    const userMsg = document.createElement("div");
    userMsg.className = "chat-msg user";
    userMsg.textContent = questionText;
    chatFeed.appendChild(userMsg);
    chatFeed.scrollTop = chatFeed.scrollHeight;

    chatInput.value = "";

    const loadingAi = document.createElement("div");
    loadingAi.className = "chat-msg ai";
    loadingAi.textContent = "🤖 Рассчитываю и анализирую...";
    chatFeed.appendChild(loadingAi);
    chatFeed.scrollTop = chatFeed.scrollHeight;

    try {
      const headers = { "Content-Type": "application/json" };
      if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

      const res = await fetch("/api/chat", {
        method: "POST",
        headers: headers,
        body: JSON.stringify({ question: questionText })
      });

      if (res.ok) {
        const data = await res.json();
        loadingAi.innerHTML = data.answer;
      } else {
        loadingAi.textContent = "❌ Не удалось получить ответ от ИИ";
      }
    } catch (err) {
      console.error(err);
      loadingAi.textContent = "❌ Ошибка соединения с ИИ сервисом";
    }
    chatFeed.scrollTop = chatFeed.scrollHeight;
  }

  if (sendAiBtn && chatInput) {
    sendAiBtn.addEventListener("click", () => sendAiQuestion(chatInput.value));
    chatInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") sendAiQuestion(chatInput.value);
    });
  }

  // --- Trends Line Chart & Author Split ---
  let trendChartInstance = null;

  async function loadTrendsChart() {
    const canvas = document.getElementById("expense-trend-chart");
    const emptyEl = document.getElementById("expense-trend-empty");
    if (!canvas || !window.Chart) return;

    try {
      const headers = {};
      if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

      const res = await fetch(`/api/analytics/trends?period=90&scope=${currentScope}`, { headers });
      if (!res.ok) return;

      const data = await res.json();
      if (!data.dates || data.dates.length < 2 || data.amounts.every(a => a === 0)) {
        canvas.style.display = "none";
        if (emptyEl) emptyEl.style.display = "block";
        return;
      }

      canvas.style.display = "block";
      if (emptyEl) emptyEl.style.display = "none";

      if (trendChartInstance) trendChartInstance.destroy();

      const ctx = canvas.getContext("2d");
      trendChartInstance = new Chart(ctx, {
        type: "line",
        data: {
          labels: data.dates.map(d => formatDate(d)),
          datasets: [{
            label: "Расходы (₽)",
            data: data.amounts,
            borderColor: "#3b82f6",
            backgroundColor: "rgba(59, 130, 246, 0.15)",
            borderWidth: 2,
            tension: 0.3,
            fill: true,
            pointRadius: 2
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: "#94a3b8", fontSize: 10 } },
            y: { ticks: { color: "#94a3b8", fontSize: 10 } }
          }
        }
      });
    } catch (err) {
      console.error("Chart load error", err);
    }
  }

  async function loadAuthorsBreakdown() {
    const container = document.getElementById("authors-breakdown-list");
    if (!container) return;

    try {
      const headers = {};
      if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

      const res = await fetch("/api/analytics/authors?period=30", { headers });
      if (!res.ok) return;

      const items = await res.json();
      if (!items || items.length === 0) {
        container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem;">Нет трат за текущий период</div>';
        return;
      }

      container.innerHTML = items.map(item => `
        <div style="margin-bottom: 8px;">
          <div style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 4px;">
            <span>👤 <strong>${item.author_name}</strong></span>
            <span><strong>${formatMoney(item.amount)}</strong> (${item.percentage}%)</span>
          </div>
          <div style="height: 6px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden;">
            <div style="width: ${item.percentage}%; height: 100%; background: var(--accent-blue);"></div>
          </div>
        </div>
      `).join("");
    } catch (err) {
      console.error("Authors breakdown error", err);
    }
  }

  // --- Subscriptions Tab & Financial Calendar ---
  let calendarDate = new Date();
  let loadedSubscriptions = [];

  const MONTH_NAMES_RU = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
  ];

  function initFinancialCalendar() {
    const prevBtn = document.getElementById("cal-prev-month");
    const nextBtn = document.getElementById("cal-next-month");

    if (prevBtn && nextBtn) {
      prevBtn.addEventListener("click", () => {
        calendarDate.setMonth(calendarDate.getMonth() - 1);
        renderFinancialCalendar();
      });
      nextBtn.addEventListener("click", () => {
        calendarDate.setMonth(calendarDate.getMonth() + 1);
        renderFinancialCalendar();
      });
    }
  }

  function renderFinancialCalendar() {
    const titleEl = document.getElementById("cal-month-title");
    const gridEl = document.getElementById("calendar-days-grid");
    const detailsBox = document.getElementById("calendar-details-box");

    if (!gridEl || !titleEl) return;

    const year = calendarDate.getFullYear();
    const month = calendarDate.getMonth();

    titleEl.textContent = `${MONTH_NAMES_RU[month]} ${year}`;
    gridEl.innerHTML = "";
    if (detailsBox) detailsBox.style.display = "none";

    const firstDayIndex = (new Date(year, month, 1).getDay() + 6) % 7; // Mon = 0
    const totalDays = new Date(year, month + 1, 0).getDate();
    const prevMonthTotalDays = new Date(year, month, 0).getDate();

    const today = new Date();
    const isCurrentMonth = today.getFullYear() === year && today.getMonth() === month;

    // Previous month padding days
    for (let i = firstDayIndex - 1; i >= 0; i--) {
      const cell = document.createElement("div");
      cell.className = "calendar-day-cell other-month";
      cell.textContent = prevMonthTotalDays - i;
      gridEl.appendChild(cell);
    }

    // Current month days
    for (let day = 1; day <= totalDays; day++) {
      const cell = document.createElement("div");
      cell.className = "calendar-day-cell";
      cell.style.cssText = "aspect-ratio: 1; border-radius: 8px; background: rgba(255, 255, 255, 0.02); border: 1px solid transparent; display: flex; flex-direction: column; align-items: center; justify-content: center; font-size: 0.8rem; font-weight: 500; color: var(--text-main); cursor: pointer; position: relative;";
      cell.textContent = day;

      if (isCurrentMonth && day === today.getDate()) {
        cell.classList.add("today");
        cell.style.borderColor = "var(--accent-blue)";
        cell.style.background = "rgba(59, 130, 246, 0.15)";
      }

      // Check subscriptions for this day
      const daySubs = loadedSubscriptions.filter(s => {
        if (s.billing_day && Number(s.billing_day) === day) return true;
        if (s.next_billing) {
          const nb = new Date(s.next_billing);
          if (nb.getFullYear() === year && nb.getMonth() === month && nb.getDate() === day) return true;
        }
        return false;
      });

      if (daySubs.length > 0) {
        cell.classList.add("has-sub");
        cell.style.color = "#38bdf8";
        const dot = document.createElement("div");
        dot.className = "calendar-sub-dot";
        dot.style.cssText = "width: 5px; height: 5px; border-radius: 50%; background: var(--accent-red); position: absolute; bottom: 4px; box-shadow: 0 0 6px var(--accent-red);";
        cell.appendChild(dot);
      }

      cell.addEventListener("click", () => {
        document.querySelectorAll(".calendar-day-cell").forEach(c => {
          c.classList.remove("selected");
          if (!c.classList.contains("today")) {
            c.style.background = "rgba(255, 255, 255, 0.02)";
            c.style.borderColor = "transparent";
          }
        });
        cell.classList.add("selected");
        cell.style.background = "rgba(59, 130, 246, 0.3)";
        cell.style.borderColor = "var(--accent-blue)";

        if (detailsBox) {
          detailsBox.style.display = "block";
          if (daySubs.length > 0) {
            const subItemsText = daySubs.map(s => `• <strong>${s.name}</strong>: ${formatMoney(s.amount)}`).join("<br>");
            detailsBox.innerHTML = `📅 <strong>${day} ${MONTH_NAMES_RU[month]}</strong>:<br>${subItemsText}`;
          } else {
            detailsBox.innerHTML = `📅 <strong>${day} ${MONTH_NAMES_RU[month]}</strong> — нет запланированных списаний.`;
          }
        }
      });

      gridEl.appendChild(cell);
    }
  }

  async function loadSubscriptions() {
    const container = document.getElementById("subs-list");
    if (!container) return;

    try {
      const headers = {};
      if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

      const res = await fetch("/api/subscriptions", { headers });
      if (!res.ok) return;

      const data = await res.json();
      loadedSubscriptions = data.subscriptions || [];

      document.getElementById("subs-total-monthly").textContent = formatMoney(data.total_monthly);
      document.getElementById("subs-total-yearly").textContent = formatMoney(data.total_yearly);

      renderFinancialCalendar();

      if (!data.subscriptions || data.subscriptions.length === 0) {
        container.innerHTML = '<div style="color: var(--text-muted); padding: 12px; text-align: center;">Подписок пока нет</div>';
        return;
      }

      container.innerHTML = data.subscriptions.map(s => {
        const periodStr = s.period === "monthly" ? "мес" : (s.period === "yearly" ? "год" : "кв");
        const nextBillingStr = s.next_billing ? formatDate(s.next_billing) : `день ${s.billing_day}`;
        return `
          <div style="background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; padding: 14px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
            <div>
              <div style="font-weight: 700; font-size: 0.95rem;">${s.name}</div>
              <div style="font-size: 0.78rem; color: var(--text-muted);">📅 След. списание: ${nextBillingStr}</div>
            </div>
            <div style="text-align: right; display: flex; align-items: center; gap: 10px;">
              <div>
                <div style="font-weight: 800; color: var(--accent-red);">${formatMoney(s.amount)}/${periodStr}</div>
              </div>
              <button class="delete-sub-btn" data-id="${s.id}" style="background: rgba(239, 68, 68, 0.15); border: none; color: var(--accent-red); padding: 6px 10px; border-radius: 6px; cursor: pointer;">🗑</button>
            </div>
          </div>
        `;
      }).join("");

      document.querySelectorAll(".delete-sub-btn").forEach(btn => {
        btn.addEventListener("click", async function () {
          const subId = this.getAttribute("data-id");
          if (!confirm("Удалить эту подписку?")) return;

          try {
            const h = { "Content-Type": "application/json" };
            if (tg && tg.initData) h["telegram-web-app-init-data"] = tg.initData;

            const dRes = await fetch(`/api/subscriptions/${subId}`, { method: "DELETE", headers: h });
            if (dRes.ok) loadSubscriptions();
          } catch (e) { console.error(e); }
        });
      });

    } catch (err) {
      console.error("Load subscriptions error", err);
    }
  }

  // Toggle Add Subscription Form
  const btnShowAddSub = document.getElementById("btn-show-add-sub");
  const addSubFormContainer = document.getElementById("add-sub-form-container");
  if (btnShowAddSub && addSubFormContainer) {
    btnShowAddSub.addEventListener("click", () => {
      addSubFormContainer.style.display = addSubFormContainer.style.display === "none" ? "block" : "none";
    });
  }

  // Save Subscription
  const btnSaveSub = document.getElementById("btn-save-sub");
  if (btnSaveSub) {
    btnSaveSub.addEventListener("click", async () => {
      const name = document.getElementById("sub-name-input").value.trim();
      const amount = parseFloat(document.getElementById("sub-amount-input").value) || 0;
      const period = document.getElementById("sub-period-select").value;
      const billing_day = parseInt(document.getElementById("sub-day-input").value) || 1;

      if (!name || amount <= 0) {
        alert("Заполните название и сумму подписки");
        return;
      }

      try {
        const headers = { "Content-Type": "application/json" };
        if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

        const res = await fetch("/api/subscriptions", {
          method: "POST",
          headers,
          body: JSON.stringify({ name, amount, period, billing_day, category: "Подписки" })
        });

        if (res.ok) {
          alert("✅ Подписка добавлена!");
          document.getElementById("sub-name-input").value = "";
          document.getElementById("sub-amount-input").value = "";
          addSubFormContainer.style.display = "none";
          loadSubscriptions();
        }
      } catch (err) {
        console.error(err);
      }
    });
  }

  // Autodetect Subscriptions Button
  const btnAutodetectSubs = document.getElementById("btn-autodetect-subs");
  if (btnAutodetectSubs) {
    btnAutodetectSubs.addEventListener("click", async () => {
      try {
        const headers = {};
        if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

        const res = await fetch("/api/subscriptions/autodetect", { headers });
        if (res.ok) {
          const data = await res.json();
          if (!data.detected || data.detected.length === 0) {
            alert("Повторяющихся подписок в истории трат не найдено.");
            return;
          }
          const msg = data.detected.map(d => `• ${d.name}: ${d.amount} ₽ (день ${d.suggested_billing_day})`).join("\n");
          if (confirm(`Найдены кандидаты в подписки:\n\n${msg}\n\nДобавить их?`)) {
            for (const sub of data.detected) {
              const h = { "Content-Type": "application/json" };
              if (tg && tg.initData) h["telegram-web-app-init-data"] = tg.initData;
              await fetch("/api/subscriptions", {
                method: "POST",
                headers: h,
                body: JSON.stringify({
                  name: sub.name,
                  amount: sub.amount,
                  period: "monthly",
                  billing_day: sub.suggested_billing_day,
                  category: "Подписки"
                })
              });
            }
            loadSubscriptions();
          }
        }
      } catch (err) {
        console.error(err);
      }
    });
  }

  // --- Compound Interest Calculator ---
  let calcChartInstance = null;

  function initCompoundCalculator() {
    const startRange = document.getElementById("calc-start");
    const monthlyRange = document.getElementById("calc-monthly");
    const monthsRange = document.getElementById("calc-months");
    const apyRange = document.getElementById("calc-apy");

    if (!startRange || !monthlyRange || !monthsRange || !apyRange) return;

    const updateCalc = () => {
      const start = Number(startRange.value);
      const monthly = Number(monthlyRange.value);
      const months = Number(monthsRange.value);
      const apy = Number(apyRange.value);

      document.getElementById("calc-val-start").textContent = formatMoney(start);
      document.getElementById("calc-val-monthly").textContent = formatMoney(monthly);
      document.getElementById("calc-val-months").textContent = `${months} мес. (${(months/12).toFixed(1).replace('.0','')} г.)`;
      document.getElementById("calc-val-apy").textContent = `${apy}%`;

      const monthlyRate = apy / 100 / 12;
      let currentBal = start;
      let totalInvested = start;

      const labels = [0];
      const dataInvested = [start];
      const dataInterest = [0];

      for (let m = 1; m <= months; m++) {
        const monthInterest = currentBal * monthlyRate;
        currentBal += monthInterest + monthly;
        totalInvested += monthly;

        if (months <= 24 || m % Math.ceil(months / 12) === 0 || m === months) {
          labels.push(`${m}м`);
          dataInvested.push(Math.round(totalInvested));
          dataInterest.push(Math.round(currentBal - totalInvested));
        }
      }

      const totalInterest = Math.max(0, currentBal - totalInvested);

      document.getElementById("calc-res-total").textContent = formatMoney(currentBal);
      document.getElementById("calc-res-dep").textContent = formatMoney(totalInvested);
      document.getElementById("calc-res-interest").textContent = "+" + formatMoney(totalInterest);

      renderCalcChart(labels, dataInvested, dataInterest);
    };

    [startRange, monthlyRange, monthsRange, apyRange].forEach(r => {
      r.addEventListener("input", updateCalc);
    });

    updateCalc();
  }

  function renderCalcChart(labels, dataInvested, dataInterest) {
    const canvas = document.getElementById("goal-calc-chart");
    if (!canvas || !window.Chart) return;

    if (calcChartInstance) calcChartInstance.destroy();

    const ctx = canvas.getContext("2d");
    calcChartInstance = new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Свои взносы (₽)",
            data: dataInvested,
            backgroundColor: "#3b82f6",
            borderRadius: 4
          },
          {
            label: "Проценты APY (₽)",
            data: dataInterest,
            backgroundColor: "#8b5cf6",
            borderRadius: 4
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: true,
            labels: { color: "#94a3b8", font: { size: 10 } }
          }
        },
        scales: {
          x: { stacked: true, ticks: { color: "#94a3b8", font: { size: 10 } } },
          y: { stacked: true, ticks: { color: "#94a3b8", font: { size: 10 } } }
        }
      }
    });
  }

  // --- Unified Challenges System ---
  const ALL_CHAL_STORAGE_KEY = "family_budget_unified_challenges_v3";

  const DEFAULT_INITIAL_CHALLENGES = [
    {
      id: "builtin_52weeks",
      title: "Челлендж «52 Недели»",
      type: "progressive",
      emoji: "🎯",
      color: "blue",
      stepRub: 100,
      stepsCount: 52,
      currentStep: 0,
      isBuiltin: true
    },
    {
      id: "builtin_30days",
      title: "30 Дней без кофе и фастфуда",
      type: "daily_bubbles",
      emoji: "☕",
      color: "green",
      days: 30,
      dailyRub: 300,
      checkedDays: [],
      isBuiltin: true
    },
    {
      id: "builtin_rounding",
      title: "Умная копилка (Округление)",
      type: "rounding",
      emoji: "🪙",
      color: "purple",
      step: 100,
      isBuiltin: true
    }
  ];

  function getChallengesList() {
    try {
      const saved = localStorage.getItem(ALL_CHAL_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch (e) { console.error(e); }
    return JSON.parse(JSON.stringify(DEFAULT_INITIAL_CHALLENGES));
  }

  function saveChallengesList(list) {
    try {
      localStorage.setItem(ALL_CHAL_STORAGE_KEY, JSON.stringify(list));
    } catch (e) { console.error(e); }
  }

  function initChallengesSystem() {
    // 1. Toggle Add Form
    const btnShowAdd = document.getElementById("btn-show-add-challenge");
    const formContainer = document.getElementById("add-challenge-form-container");
    if (btnShowAdd && formContainer) {
      btnShowAdd.addEventListener("click", () => {
        formContainer.style.display = formContainer.style.display === "none" ? "block" : "none";
      });
    }

    // 2. Type change dropdown
    const typeSelect = document.getElementById("chal-custom-type");
    const pDaily = document.getElementById("chal-params-daily");
    const pProg = document.getElementById("chal-params-progressive");
    const pTgt = document.getElementById("chal-params-target");

    if (typeSelect) {
      typeSelect.addEventListener("change", function () {
        const val = this.value;
        if (pDaily) pDaily.style.display = val === "daily_bubbles" ? "block" : "none";
        if (pProg) pProg.style.display = val === "progressive" ? "block" : "none";
        if (pTgt) pTgt.style.display = val === "target_goal" ? "block" : "none";
      });
    }

    // 3. Emoji picker selection
    let selectedEmoji = "🎯";
    const emojiChips = document.querySelectorAll(".emoji-chip");
    emojiChips.forEach(chip => {
      chip.addEventListener("click", function () {
        emojiChips.forEach(c => {
          c.classList.remove("active");
          c.style.border = "1px solid var(--card-border)";
          c.style.background = "var(--card-bg)";
        });
        this.classList.add("active");
        this.style.border = "1px solid var(--accent-blue)";
        this.style.background = "rgba(59,130,246,0.2)";
        selectedEmoji = this.getAttribute("data-emoji");
      });
    });

    // 4. Color picker selection
    let selectedColor = "blue";
    const colorChips = document.querySelectorAll(".color-chip");
    colorChips.forEach(chip => {
      chip.addEventListener("click", function () {
        colorChips.forEach(c => {
          c.classList.remove("active");
          c.style.border = "1px solid var(--card-border)";
        });
        this.classList.add("active");
        this.style.border = "2px solid white";
        selectedColor = this.getAttribute("data-color");
      });
    });

    // 5. Save new challenge button
    const btnSave = document.getElementById("btn-save-custom-challenge");
    if (btnSave) {
      btnSave.addEventListener("click", () => {
        const title = document.getElementById("chal-custom-title").value.trim();
        if (!title) {
          alert("Пожалуйста, введите название челленджа");
          return;
        }

        const type = typeSelect ? typeSelect.value : "daily_bubbles";
        const newChallenge = {
          id: "chal_" + Date.now(),
          title: title,
          type: type,
          emoji: selectedEmoji,
          color: selectedColor,
          days: parseInt(document.getElementById("chal-custom-days").value) || 14,
          dailyRub: parseFloat(document.getElementById("chal-custom-daily-rub").value) || 200,
          stepRub: parseFloat(document.getElementById("chal-custom-step-rub").value) || 100,
          stepsCount: parseInt(document.getElementById("chal-custom-steps-count").value) || 12,
          targetRub: parseFloat(document.getElementById("chal-custom-target-rub").value) || 30000,
          depositRub: parseFloat(document.getElementById("chal-custom-deposit-rub").value) || 1000,
          checkedDays: [],
          currentStep: 0,
          currentSaved: 0
        };

        const list = getChallengesList();
        list.unshift(newChallenge);
        saveChallengesList(list);

        document.getElementById("chal-custom-title").value = "";
        if (formContainer) formContainer.style.display = "none";

        renderAllChallenges();
      });
    }

    renderAllChallenges();
  }

  function renderAllChallenges() {
    const container = document.getElementById("all-challenges-container");
    if (!container) return;

    const list = getChallengesList();
    if (list.length === 0) {
      container.innerHTML = '<div style="color: var(--text-muted); text-align: center; padding: 20px;">Нет активных челленджей. Нажмите «➕ Создать свой», чтобы добавить!</div>';
      return;
    }

    const getColorVar = (col) => {
      if (col === "green") return "var(--accent-green)";
      if (col === "purple") return "var(--accent-purple)";
      if (col === "red") return "var(--accent-red)";
      return "var(--accent-blue)";
    };

    container.innerHTML = "";

    list.forEach(chal => {
      const card = document.createElement("div");
      card.className = "challenge-card";
      const colorHex = getColorVar(chal.color);

      if (chal.type === "daily_bubbles") {
        const checkedArr = chal.checkedDays || [];
        const count = checkedArr.length;
        const totalSaved = count * chal.dailyRub;
        const progressPct = Math.min(100, Math.round((count / chal.days) * 100));

        card.innerHTML = `
          <div class="challenge-title">
            <span>${chal.emoji} ${chal.title}</span>
            <span style="color: ${colorHex};">${formatMoney(totalSaved)} сэкономлено</span>
          </div>
          <div style="display: flex; justify-content: space-between; font-size: 0.8rem; color: var(--text-muted); margin-bottom: 4px;">
            <span>Цель: ${chal.days} дней (~${formatMoney(chal.dailyRub)}/день)</span>
            <span>${count} / ${chal.days} дн</span>
          </div>
          <div class="challenge-progress-bar">
            <div class="challenge-progress-fill" style="width: ${progressPct}%; background: ${colorHex};"></div>
          </div>
          <div style="display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; margin-top: 12px;" class="custom-grid-bubbles">
          </div>
          <div style="text-align: right; margin-top: 10px;">
            <button class="delete-chal-btn" data-id="${chal.id}" style="background: rgba(239, 68, 68, 0.15); border: none; color: var(--accent-red); padding: 4px 10px; border-radius: 6px; cursor: pointer; font-size: 0.78rem;">🗑 Удалить челлендж</button>
          </div>
        `;

        const bubblesGrid = card.querySelector(".custom-grid-bubbles");
        for (let i = 1; i <= chal.days; i++) {
          const bubble = document.createElement("div");
          const isChecked = checkedArr.includes(i);
          bubble.className = "challenge-bubble" + (isChecked ? " checked" : "");
          bubble.style.cssText = "aspect-ratio: 1; border-radius: 50%; border: 1.5px solid var(--card-border); background: rgba(255, 255, 255, 0.03); display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 600; color: var(--text-muted); cursor: pointer; user-select: none;";
          if (isChecked) {
            bubble.style.background = colorHex;
            bubble.style.borderColor = colorHex;
            bubble.style.color = "white";
            bubble.style.boxShadow = `0 0 10px ${colorHex}`;
          }
          bubble.textContent = isChecked ? "✓" : i;

          bubble.addEventListener("click", () => {
            let current = chal.checkedDays || [];
            if (current.includes(i)) {
              current = current.filter(x => x !== i);
            } else {
              current.push(i);
            }
            chal.checkedDays = current;
            const fullList = getChallengesList();
            const idx = fullList.findIndex(c => c.id === chal.id);
            if (idx !== -1) fullList[idx] = chal;
            saveChallengesList(fullList);
            renderAllChallenges();
          });
          bubblesGrid.appendChild(bubble);
        }

      } else if (chal.type === "progressive") {
        const k = chal.currentStep || 0;
        const totalSaved = chal.stepRub * (k * (k + 1)) / 2;
        const nextAmount = (k + 1) * chal.stepRub;
        const targetTotal = chal.stepRub * (chal.stepsCount * (chal.stepsCount + 1)) / 2;
        const progressPct = Math.min(100, Math.round((k / chal.stepsCount) * 100));

        card.innerHTML = `
          <div class="challenge-title">
            <span>${chal.emoji} ${chal.title}</span>
            <span style="color: ${colorHex};">${formatMoney(totalSaved)} / ${formatMoney(targetTotal)}</span>
          </div>
          <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 4px;">
            Каждую неделю +${formatMoney(chal.stepRub)}. Пройдено: <strong style="color: var(--text-main);">${k} из ${chal.stepsCount} шагов</strong>
          </div>
          <div class="challenge-progress-bar">
            <div class="challenge-progress-fill" style="width: ${progressPct}%; background: ${colorHex};"></div>
          </div>
          <div style="display: flex; gap: 8px; margin-top: 12px;">
            <button class="add-prog-step-btn" data-id="${chal.id}" style="flex: 2; padding: 10px; border-radius: 8px; border: none; background: ${colorHex}; color: white; font-weight: 700; font-size: 0.85rem; cursor: pointer;">
              ➕ Внести шаг (${formatMoney(nextAmount)})
            </button>
            <button class="reset-prog-btn" data-id="${chal.id}" style="padding: 10px; border-radius: 8px; border: 1px solid var(--card-border); background: transparent; color: var(--text-muted); font-size: 0.8rem; cursor: pointer;">
              Сброс
            </button>
            <button class="delete-chal-btn" data-id="${chal.id}" style="padding: 10px; border-radius: 8px; border: 1px solid var(--card-border); background: transparent; color: var(--accent-red); font-size: 0.8rem; cursor: pointer;">
              🗑
            </button>
          </div>
        `;

        card.querySelector(".add-prog-step-btn").addEventListener("click", () => {
          if ((chal.currentStep || 0) < chal.stepsCount) {
            chal.currentStep = (chal.currentStep || 0) + 1;
            const fullList = getChallengesList();
            const idx = fullList.findIndex(c => c.id === chal.id);
            if (idx !== -1) fullList[idx] = chal;
            saveChallengesList(fullList);
            renderAllChallenges();
          } else {
            alert("🎉 Поздравляем! Челлендж завершен!");
          }
        });

        card.querySelector(".reset-prog-btn").addEventListener("click", () => {
          if (confirm("Сбросить прогресс этого челленджа?")) {
            chal.currentStep = 0;
            const fullList = getChallengesList();
            const idx = fullList.findIndex(c => c.id === chal.id);
            if (idx !== -1) fullList[idx] = chal;
            saveChallengesList(fullList);
            renderAllChallenges();
          }
        });

      } else if (chal.type === "target_goal") {
        const saved = chal.currentSaved || 0;
        const progressPct = Math.min(100, Math.round((saved / chal.targetRub) * 100));

        card.innerHTML = `
          <div class="challenge-title">
            <span>${chal.emoji} ${chal.title}</span>
            <span style="color: ${colorHex};">${formatMoney(saved)} / ${formatMoney(chal.targetRub)}</span>
          </div>
          <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 4px;">
            Целевое накопление. Прогресс: <strong style="color: var(--text-main);">${progressPct}%</strong>
          </div>
          <div class="challenge-progress-bar">
            <div class="challenge-progress-fill" style="width: ${progressPct}%; background: ${colorHex};"></div>
          </div>
          <div style="display: flex; gap: 8px; margin-top: 12px;">
            <button class="add-target-dep-btn" data-id="${chal.id}" style="flex: 2; padding: 10px; border-radius: 8px; border: none; background: ${colorHex}; color: white; font-weight: 700; font-size: 0.85rem; cursor: pointer;">
              ➕ Пополнить (+${formatMoney(chal.depositRub)})
            </button>
            <button class="delete-chal-btn" data-id="${chal.id}" style="flex: 1; padding: 10px; border-radius: 8px; border: 1px solid var(--card-border); background: transparent; color: var(--accent-red); font-size: 0.8rem; cursor: pointer;">
              🗑 Удалить
            </button>
          </div>
        `;

        card.querySelector(".add-target-dep-btn").addEventListener("click", () => {
          chal.currentSaved = (chal.currentSaved || 0) + chal.depositRub;
          const fullList = getChallengesList();
          const idx = fullList.findIndex(c => c.id === chal.id);
          if (idx !== -1) fullList[idx] = chal;
          saveChallengesList(fullList);
          renderAllChallenges();
        });

      } else if (chal.type === "rounding") {
        const step = chal.step || 100;
        const estMonthly = step === 10 ? 320 : (step === 50 ? 1600 : 3200);

        card.innerHTML = `
          <div class="challenge-title">
            <span>${chal.emoji} ${chal.title}</span>
            <span style="color: ${colorHex};">~ ${formatMoney(estMonthly)}/мес</span>
          </div>
          <div style="font-size: 0.8rem; color: var(--text-muted);">
            Автоматическое округление ваших трат отправляется в накопительный счёт. Выберите шаг:
          </div>
          <div class="rounding-options" style="display: flex; gap: 8px; margin-top: 10px;">
            <div class="rounding-chip ${step === 10 ? 'active' : ''}" data-step="10" style="flex: 1; padding: 8px; text-align: center; border-radius: 8px; border: 1px solid var(--card-border); background: ${step === 10 ? 'rgba(139, 92, 246, 0.2)' : 'rgba(255, 255, 255, 0.04)'}; font-size: 0.8rem; font-weight: 600; cursor: pointer;">До 10 ₽</div>
            <div class="rounding-chip ${step === 50 ? 'active' : ''}" data-step="50" style="flex: 1; padding: 8px; text-align: center; border-radius: 8px; border: 1px solid var(--card-border); background: ${step === 50 ? 'rgba(139, 92, 246, 0.2)' : 'rgba(255, 255, 255, 0.04)'}; font-size: 0.8rem; font-weight: 600; cursor: pointer;">До 50 ₽</div>
            <div class="rounding-chip ${step === 100 ? 'active' : ''}" data-step="100" style="flex: 1; padding: 8px; text-align: center; border-radius: 8px; border: 1px solid var(--card-border); background: ${step === 100 ? 'rgba(139, 92, 246, 0.2)' : 'rgba(255, 255, 255, 0.04)'}; font-size: 0.8rem; font-weight: 600; cursor: pointer;">До 100 ₽</div>
          </div>
          <div style="text-align: right; margin-top: 10px;">
            <button class="delete-chal-btn" data-id="${chal.id}" style="background: rgba(239, 68, 68, 0.15); border: none; color: var(--accent-red); padding: 4px 10px; border-radius: 6px; cursor: pointer; font-size: 0.78rem;">🗑 Удалить челлендж</button>
          </div>
        `;

        card.querySelectorAll(".rounding-chip").forEach(chip => {
          chip.addEventListener("click", () => {
            chal.step = Number(chip.getAttribute("data-step"));
            const fullList = getChallengesList();
            const idx = fullList.findIndex(c => c.id === chal.id);
            if (idx !== -1) fullList[idx] = chal;
            saveChallengesList(fullList);
            renderAllChallenges();
          });
        });
      }

      card.querySelectorAll(".delete-chal-btn").forEach(btn => {
        btn.addEventListener("click", () => {
          if (confirm("Удалить этот челлендж?")) {
            let fullList = getChallengesList();
            fullList = fullList.filter(c => c.id !== chal.id);
            saveChallengesList(fullList);
            renderAllChallenges();
          }
        });
      });

      container.appendChild(card);
    });
  }

  // --- Operations Tab Manager ---
  async function loadOperationsTabList() {
    const container = document.getElementById("operations-tab-list");
    if (!container) return;

    try {
      const headers = getAuthHeaders();
      const res = await fetch(`/api/transactions?scope=${currentScope}`, { headers });
      if (!res.ok) return;

      const txs = await res.json();
      if (!txs || txs.length === 0) {
        container.innerHTML = '<div style="color: var(--text-muted); padding: 12px; text-align: center;">Операций пока нет</div>';
        return;
      }

      container.innerHTML = txs.map(tx => {
        const typeEmoji = tx.type === "income" ? "➕" : (tx.type === "expense" ? "💸" : "🔄");
        const typeClass = tx.type;
        const catStr = tx.category ? ` • ${tx.category}` : "";
        return `
          <div style="background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 10px; padding: 12px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
            <div>
              <div style="font-weight: 700; font-size: 0.9rem;">${typeEmoji} ${tx.note || tx.category || "Операция"}</div>
              <div style="font-size: 0.78rem; color: var(--text-muted);">${formatDate(tx.date)}${catStr}</div>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
              <div style="font-weight: 800;" class="${typeClass}">${formatMoney(tx.amount)}</div>
              <button class="op-edit-btn" data-id="${tx.id}" data-note="${tx.note || ''}" data-amount="${tx.amount}" data-cat="${tx.category || ''}" style="background: rgba(59, 130, 246, 0.15); border: none; color: var(--accent-blue); padding: 4px 8px; border-radius: 6px; cursor: pointer; font-size: 0.8rem;">✏️</button>
              <button class="op-delete-btn" data-id="${tx.id}" style="background: rgba(239, 68, 68, 0.15); border: none; color: var(--accent-red); padding: 4px 8px; border-radius: 6px; cursor: pointer; font-size: 0.8rem;">🗑</button>
            </div>
          </div>
        `;
      }).join("");

      document.querySelectorAll(".op-delete-btn").forEach(btn => {
        btn.addEventListener("click", async function () {
          const opId = this.getAttribute("data-id");
          if (!confirm("Удалить эту операцию?")) return;

          try {
            const h = getAuthHeaders();
            const dRes = await fetch(`/api/operations/${opId}`, { method: "DELETE", headers: h });
            if (dRes.ok) {
              loadSummary();
              loadOperationsTabList();
            } else {
              alert("Нельзя удалить чужую операцию или ошибка сервера");
            }
          } catch (e) { console.error(e); }
        });
      });

      document.querySelectorAll(".op-edit-btn").forEach(btn => {
        btn.addEventListener("click", async function () {
          const opId = this.getAttribute("data-id");
          const oldNote = this.getAttribute("data-note");
          const oldAmount = this.getAttribute("data-amount");

          const newNote = prompt("Новое описание операции:", oldNote);
          if (newNote === null) return;

          const newAmountStr = prompt("Новая сумма (₽):", oldAmount);
          const newAmount = parseFloat(newAmountStr);
          if (!newAmount || newAmount <= 0) return;

          try {
            const h = getAuthHeaders();
            h["Content-Type"] = "application/json";

            const uRes = await fetch(`/api/operations/${opId}`, {
              method: "PUT",
              headers: h,
              body: JSON.stringify({ note: newNote, amount: newAmount })
            });

            if (uRes.ok) {
              loadSummary();
              loadOperationsTabList();
            }
          } catch (e) { console.error(e); }
        });
      });

    } catch (err) {
      console.error("Load operations tab list error", err);
    }
  }

  // --- Profile & Virtual Card Loader ---
  const CAT_LOVE_MESSAGES = [
    "🐾 «Вы лучшая пара котиков! Считаем мур-бюджет вместе с любовью ❤️»",
    "😻 «Котики копят на общие мечты и вкусняшки! Ты супер! 🐟»",
    "💕 «Любовь + Финансы = Счастливая мур-семья 🐱✨»",
    "🐾 «Вместе мы накопим на самый большой кошачий домик! 🏠💖»",
    "🐱 «Мурр! Один котик тратит, второй подстрахует — идеальная команда! 🤝»"
  ];

  let isCardFlipped = false;
  const cardFlipper = document.getElementById("virtual-card-flipper");
  if (cardFlipper) {
    cardFlipper.addEventListener("click", () => {
      const inner = document.getElementById("virtual-card-inner");
      if (!inner) return;
      isCardFlipped = !isCardFlipped;
      inner.style.transform = isCardFlipped ? "rotateY(180deg)" : "rotateY(0deg)";
    });
  }

  async function loadUserProfile() {
    try {
      const headers = getAuthHeaders();
      let prof = {};
      const res = await fetch(apiUrl("/api/profile"), { headers });
      if (res.ok) {
        prof = await res.json();
      }

      const tgUser = (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initDataUnsafe) ? window.Telegram.WebApp.initDataUnsafe.user : null;

      // Очищаем localStorage от старых \"мусорных\" значений перед записью новых
      let cachedFname = ""; try { cachedFname = localStorage.getItem("user_first_name") || ""; } catch(e){}
      if (cachedFname === "Пользователь" || cachedFname === "") { try { localStorage.removeItem("user_first_name"); } catch(e){} cachedFname = ""; }
      let cachedLname = ""; try { cachedLname = localStorage.getItem("user_last_name") || ""; } catch(e){}
      if (cachedLname === "Пользователь") { try { localStorage.removeItem("user_last_name"); } catch(e){} cachedLname = ""; }
      let cachedUname = ""; try { cachedUname = localStorage.getItem("user_username") || ""; } catch(e){}
      let cachedPhoto = ""; try { cachedPhoto = localStorage.getItem("user_photo_url") || ""; } catch(e){}
      let cachedUid = ""; try { cachedUid = localStorage.getItem("user_uid") || ""; } catch(e){}
      if (cachedUid === "123456789" || cachedUid === "12345" || cachedUid === "1") { try { localStorage.removeItem("user_uid"); } catch(e){} cachedUid = ""; }

      // Сохраняем данные из Telegram только если они корректные
      if (tgUser) {
        if (tgUser.first_name && tgUser.first_name !== "Пользователь") { try { localStorage.setItem("user_first_name", tgUser.first_name); cachedFname = tgUser.first_name; } catch(e){} }
        if (tgUser.last_name && tgUser.last_name !== "Пользователь") { try { localStorage.setItem("user_last_name", tgUser.last_name); cachedLname = tgUser.last_name; } catch(e){} }
        if (tgUser.username) { try { localStorage.setItem("user_username", tgUser.username); cachedUname = tgUser.username; } catch(e){} }
        if (tgUser.photo_url) { try { localStorage.setItem("user_photo_url", tgUser.photo_url); cachedPhoto = tgUser.photo_url; } catch(e){} }
        if (tgUser.id && String(tgUser.id) !== "123456789" && String(tgUser.id) !== "12345" && String(tgUser.id) !== "1") { try { localStorage.setItem("user_uid", String(tgUser.id)); cachedUid = String(tgUser.id); } catch(e){} }
      }

      // Переопределяем cached переменные после возможного обновления
      cachedFname = ""; try { cachedFname = localStorage.getItem("user_first_name") || ""; } catch(e){}
      cachedLname = ""; try { cachedLname = localStorage.getItem("user_last_name") || ""; } catch(e){}
      cachedUname = ""; try { cachedUname = localStorage.getItem("user_username") || ""; } catch(e){}
      cachedPhoto = ""; try { cachedPhoto = localStorage.getItem("user_photo_url") || ""; } catch(e){}
      cachedUid = ""; try { cachedUid = localStorage.getItem("user_uid") || ""; } catch(e){}

      const photoUrl = prof.photo_url || (tgUser && tgUser.photo_url) || cachedPhoto || "";
      const username = prof.username || (tgUser && tgUser.username) || cachedUname || "";
      const rawFname = prof.first_name;

      let firstName = "";
      if (rawFname && rawFname !== "Пользователь") {
        firstName = rawFname;
      } else if (tgUser && tgUser.first_name && tgUser.first_name !== "Пользователь") {
        firstName = tgUser.first_name;
      } else if (cachedFname && cachedFname !== "Пользователь") {
        firstName = cachedFname;
      } else if (username) {
        firstName = username.replace(/^@/, '');
      } else {
        firstName = "Пользователь";
      }

      const lastName = prof.last_name || (tgUser && tgUser.last_name) || cachedLname || "";
      const fullName = (firstName + " " + lastName).trim();
      const rawTgId = prof.telegram_id;
      
      // Приоритет получения ID: профиль с сервера > initDataUnsafe > URL параметр uid > localStorage
      let tgId = null;
      if (rawTgId && String(rawTgId) !== "1" && String(rawTgId) !== "123456789" && String(rawTgId) !== "12345") {
        tgId = rawTgId;
      } else if (tgUser && tgUser.id && String(tgUser.id) !== "123456789" && String(tgUser.id) !== "12345" && String(tgUser.id) !== "1") {
        tgId = tgUser.id;
      } else if (getUid() && String(getUid()) !== "1" && String(getUid()) !== "123456789" && String(getUid()) !== "12345") {
        tgId = getUid();
      } else if (cachedUid && String(cachedUid) !== "123456789" && String(cachedUid) !== "12345" && String(cachedUid) !== "1") {
        tgId = cachedUid;
      }
      
      // Если так и не нашли валидный ID, используем заглушку, но не сохраняем её
      if (!tgId) {
        tgId = "••••••••";
      }

      const avatarContainer = document.getElementById("profile-avatar-container");
      const nameEl = document.getElementById("profile-name");
      const tagEl = document.getElementById("profile-tag");
      const idEl = document.getElementById("profile-id");
      const incEl = document.getElementById("profile-income");
      const expEl = document.getElementById("profile-expense");
      const rateEl = document.getElementById("profile-savings-rate");
      const shareEl = document.getElementById("profile-family-share");

      if (avatarContainer) {
        if (photoUrl) {
          avatarContainer.innerHTML = `<img src="${photoUrl}" style="width: 52px; height: 52px; border-radius: 50%; border: 2px solid white; object-fit: cover; box-shadow: 0 2px 8px rgba(0,0,0,0.3);" alt="Avatar">`;
        } else {
          const letter = firstName.charAt(0).toUpperCase() || "🐱";
          avatarContainer.innerHTML = `<div style="width: 52px; height: 52px; border-radius: 50%; background: rgba(255,255,255,0.3); display: flex; align-items: center; justify-content: center; font-size: 1.5rem; font-weight: 800; color: white;">${letter}</div>`;
        }
      }

      if (nameEl) nameEl.textContent = fullName;
      if (tagEl) {
        if (username) {
          tagEl.textContent = `@${username.replace(/^@/, '')}`;
          tagEl.style.display = "block";
        } else {
          tagEl.style.display = "none";
        }
      }
      const streakBadge = document.getElementById("profile-streak-badge");
      if (streakBadge) {
        const streakCount = prof.streak_count || 0;
        streakBadge.innerHTML = `<i class="fa-solid fa-fire" style="color: #f97316; margin-right: 4px;"></i> ${streakCount} дн.`;
      }

      // Generate card number from telegram ID into 4 separate grid spans
      const cardNumEl = document.getElementById("profile-card-number");
      if (cardNumEl) {
        const rawId = String(tgId).padStart(16, "5248");
        const parts = rawId.match(/.{1,4}/g) || ["••••", "••••", "••••", "••••"];
        cardNumEl.innerHTML = parts.map(p => `<span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${p}</span>`).join("");
      }

      if (idEl) idEl.innerHTML = `<i class="fa-brands fa-telegram" style="color: #38bdf8; margin-right: 5px;"></i> ID: ${tgId}`;
      if (incEl) incEl.textContent = "+" + formatMoney(prof.personal_income_month || 0);
      if (expEl) expEl.textContent = "-" + formatMoney(prof.personal_expense_month || 0);
      if (rateEl) rateEl.textContent = (prof.personal_savings_rate || 0).toFixed(1) + "%";
      if (shareEl) shareEl.textContent = (prof.family_share_pct || 0).toFixed(1) + "%";

      // Card back elements
      const backInc = document.getElementById("card-back-income");
      const backExp = document.getElementById("card-back-expense");
      const backRate = document.getElementById("card-back-savings-rate");
      const backMsg = document.getElementById("profile-cat-love-message");

      if (backInc) backInc.textContent = "+" + formatMoney(prof.personal_income_month || 0);
      if (backExp) backExp.textContent = "-" + formatMoney(prof.personal_expense_month || 0);
      if (backRate) backRate.textContent = (prof.personal_savings_rate || 0).toFixed(1) + "%";

      if (backMsg) {
        const randomMsg = CAT_LOVE_MESSAGES[Math.floor(Math.random() * CAT_LOVE_MESSAGES.length)];
        backMsg.textContent = randomMsg;
      }
    } catch (e) { console.error("Profile load error", e); }
  }

  // --- Dynamic Income Sources & User Settings ---
  let userIncomeSources = [];

  function renderIncomeSources() {
    const container = document.getElementById("income-sources-list");
    if (!container) return;

    if (!userIncomeSources || userIncomeSources.length === 0) {
      container.innerHTML = `
        <div style="color: var(--text-muted); font-size: 0.82rem; text-align: center; padding: 12px; background: var(--card-bg); border-radius: var(--radius); border: 1px solid var(--card-border);">
          Нет добавленных источников дохода. Нажмите «➕ Добавить».
        </div>
      `;
      return;
    }

    container.innerHTML = userIncomeSources.map((src, idx) => {
      let freqText = "";
      if (src.period === "1_monthly") freqText = `1 раз в месяц (${src.day1}-го числа)`;
      else if (src.period === "2_monthly") freqText = `2 раза в месяц (${src.day1}-го и ${src.day2}-го)`;
      else if (src.period === "weekly") freqText = "Каждую неделю";
      else freqText = "Каждый день";

      let typeText = src.type === "fixed" ? (src.amountKnown === "yes" ? `Оклад: ${formatMoney(src.amount)}` : "Оклад (сумма разная)") : "Переменный доход";

      return `
        <div style="background: var(--card-bg); border: 1px solid var(--card-border); border-radius: var(--radius); padding: 12px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
          <div>
            <div style="font-weight: 700; font-size: 0.9rem; color: var(--text-main);">💼 ${src.name}</div>
            <div style="font-size: 0.78rem; color: var(--text-muted); margin-top: 2px;">📅 ${freqText}</div>
            <div style="font-size: 0.78rem; color: var(--accent-green); font-weight: 600; margin-top: 2px;">💰 ${typeText}</div>
          </div>
          <button class="delete-inc-src-btn" data-idx="${idx}" style="background: rgba(239, 68, 68, 0.15); border: none; color: var(--accent-red); padding: 6px 10px; border-radius: 8px; cursor: pointer; font-size: 0.8rem; font-weight: 600;">🗑</button>
        </div>
      `;
    }).join("");

    container.querySelectorAll(".delete-inc-src-btn").forEach(btn => {
      btn.addEventListener("click", function () {
        const i = parseInt(this.getAttribute("data-idx"));
        userIncomeSources.splice(i, 1);
        saveIncomeSources();
        renderIncomeSources();
      });
    });
  }

  async function saveIncomeSources() {
    try {
      const headers = getAuthHeaders();
      headers["Content-Type"] = "application/json";
      await fetch(apiUrl("/api/user-settings"), {
        method: "POST",
        headers,
        body: JSON.stringify({ income_sources: JSON.stringify(userIncomeSources) })
      });
    } catch (e) { console.error("Save income sources error", e); }
  }

  async function loadUserSettings() {
    try {
      const headers = getAuthHeaders();
      const res = await fetch(apiUrl("/api/user-settings"), { headers });
      if (!res.ok) return;

      const settings = await res.json();

      if (settings.income_sources) {
        try {
          userIncomeSources = JSON.parse(settings.income_sources);
        } catch (e) { userIncomeSources = []; }
      }
      renderIncomeSources();

      const rEssSlider = document.getElementById("ratio-ess-slider");
      const rPersSlider = document.getElementById("ratio-pers-slider");
      const rSavSlider = document.getElementById("ratio-sav-slider");

      if (rEssSlider) rEssSlider.value = settings.budget_ratio_essential || 50;
      if (rPersSlider) rPersSlider.value = settings.budget_ratio_personal || 30;
      if (rSavSlider) rSavSlider.value = settings.budget_ratio_savings || 20;

      updateBudgetAllocationRatiosUI();
    } catch (e) { console.error("Load user settings error", e); }
  }

  function updateBudgetAllocationRatiosUI() {
    const ess = parseInt(document.getElementById("ratio-ess-slider")?.value) || 50;
    const pers = parseInt(document.getElementById("ratio-pers-slider")?.value) || 30;
    const sav = parseInt(document.getElementById("ratio-sav-slider")?.value) || 20;

    const essValEl = document.getElementById("ratio-ess-val");
    const persValEl = document.getElementById("ratio-pers-val");
    const savValEl = document.getElementById("ratio-sav-val");

    if (essValEl) essValEl.textContent = ess + "%";
    if (persValEl) persValEl.textContent = pers + "%";
    if (savValEl) savValEl.textContent = sav + "%";

    let salaryAmt = 0;
    userIncomeSources.forEach(s => {
      if (s.amountKnown === "yes") salaryAmt += (Number(s.amount) || 0);
    });
    if (salaryAmt === 0) salaryAmt = 75000;

    const essRubEl = document.getElementById("ratio-ess-rub");
    const persRubEl = document.getElementById("ratio-pers-rub");
    const savRubEl = document.getElementById("ratio-sav-rub");

    if (essRubEl) essRubEl.textContent = formatMoney(salaryAmt * (ess / 100));
    if (persRubEl) persRubEl.textContent = formatMoney(salaryAmt * (pers / 100));
    if (savRubEl) savRubEl.textContent = formatMoney(salaryAmt * (sav / 100));
  }

  function initUserSettings() {
    const rEssSlider = document.getElementById("ratio-ess-slider");
    const rPersSlider = document.getElementById("ratio-pers-slider");
    const rSavSlider = document.getElementById("ratio-sav-slider");

    [rEssSlider, rPersSlider, rSavSlider].forEach(el => {
      if (el) el.addEventListener("input", updateBudgetAllocationRatiosUI);
    });

    // Add Income Source Form Logic
    const btnShowAddInc = document.getElementById("btn-show-add-income");
    const addIncForm = document.getElementById("add-income-form");
    const incSchedSelect = document.getElementById("inc-schedule-select");
    const incDay2Box = document.getElementById("inc-day2-box");
    const incDaysContainer = document.getElementById("inc-days-container");
    const incTypeSelect = document.getElementById("inc-type-select");
    const incKnownBox = document.getElementById("inc-amount-known-box");
    const incKnownSelect = document.getElementById("inc-known-select");
    const incAmountValBox = document.getElementById("inc-amount-val-box");

    if (btnShowAddInc && addIncForm) {
      btnShowAddInc.addEventListener("click", () => {
        const isHidden = addIncForm.style.display === "none";
        addIncForm.style.display = isHidden ? "block" : "none";
      });
    }

    if (incSchedSelect) {
      incSchedSelect.addEventListener("change", function () {
        const val = this.value;
        if (val === "2_monthly") {
          incDaysContainer.style.display = "flex";
          incDay2Box.style.display = "block";
        } else if (val === "1_monthly") {
          incDaysContainer.style.display = "flex";
          incDay2Box.style.display = "none";
        } else {
          incDaysContainer.style.display = "none";
        }
      });
    }

    if (incTypeSelect) {
      incTypeSelect.addEventListener("change", function () {
        if (this.value === "fixed") {
          incKnownBox.style.display = "block";
          if (incKnownSelect?.value === "yes") incAmountValBox.style.display = "block";
        } else {
          incKnownBox.style.display = "none";
          incAmountValBox.style.display = "none";
        }
      });
    }

    if (incKnownSelect) {
      incKnownSelect.addEventListener("change", function () {
        incAmountValBox.style.display = (this.value === "yes" && incTypeSelect?.value === "fixed") ? "block" : "none";
      });
    }

    const btnSaveIncSrc = document.getElementById("btn-save-income-source");
    if (btnSaveIncSrc) {
      btnSaveIncSrc.addEventListener("click", () => {
        const name = document.getElementById("inc-name-input")?.value.trim() || "Работа";
        const period = incSchedSelect?.value || "1_monthly";
        const d1 = parseInt(document.getElementById("inc-day1-input")?.value) || 10;
        const d2 = parseInt(document.getElementById("inc-day2-input")?.value) || 25;
        const type = incTypeSelect?.value || "fixed";
        const known = incKnownSelect?.value || "yes";
        const amt = parseFloat(document.getElementById("inc-amount-input")?.value) || 0;

        userIncomeSources.push({
          name: name,
          period: period,
          day1: d1,
          day2: d2,
          type: type,
          amountKnown: known,
          amount: amt
        });

        saveIncomeSources();
        renderIncomeSources();
        updateBudgetAllocationRatiosUI();

        if (addIncForm) addIncForm.style.display = "none";
        alert("✅ Источник дохода добавлен!");
      });
    }

    const btnSaveRatios = document.getElementById("btn-save-budget-ratios");
    if (btnSaveRatios) {
      btnSaveRatios.addEventListener("click", async () => {
        const ess = parseInt(rEssSlider?.value) || 50;
        const pers = parseInt(rPersSlider?.value) || 30;
        const sav = parseInt(rSavSlider?.value) || 20;

        try {
          const headers = getAuthHeaders();
          headers["Content-Type"] = "application/json";
          const res = await fetch(apiUrl("/api/user-settings"), {
            method: "POST",
            headers,
            body: JSON.stringify({
              budget_ratio_essential: ess,
              budget_ratio_personal: pers,
              budget_ratio_savings: sav
            })
          });
          if (res.ok) alert("✅ Правила распределения сохранены!");
        } catch (e) { console.error(e); }
      });
    }

    loadUserSettings();
  }

  // Init inside DOMContentLoaded
  initFinancialCalendar();
  initCompoundCalculator();
  initChallengesSystem();
  initUserSettings();

  loadSummary();
  loadTrendsChart();
  loadAuthorsBreakdown();
  loadSubscriptions();
  loadOperationsTabList();
  loadUserProfile();
});


