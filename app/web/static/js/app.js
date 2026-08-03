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

  async function loadSummary() {
    try {
      const headers = getAuthHeaders();

      const res = await fetch(`/api/summary?scope=${currentScope}`, { headers });
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
        target_account: document.getElementById("op-target-account").value
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
      cell.textContent = day;

      if (isCurrentMonth && day === today.getDate()) {
        cell.classList.add("today");
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
        const dot = document.createElement("div");
        dot.className = "calendar-sub-dot";
        cell.appendChild(dot);
      }

      cell.addEventListener("click", () => {
        document.querySelectorAll(".calendar-day-cell").forEach(c => c.classList.remove("selected"));
        cell.classList.add("selected");

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

  // --- Savings Challenges Logic ---
  const CHAL_STORAGE_KEY = "family_budget_challenges_v1";

  function getChallengeState() {
    try {
      const saved = localStorage.getItem(CHAL_STORAGE_KEY);
      if (saved) return JSON.parse(saved);
    } catch (e) { console.error(e); }
    return { fiftyTwoWeeks: 0, thirtyDays: [], roundingStep: 100 };
  }

  function saveChallengeState(state) {
    try {
      localStorage.setItem(CHAL_STORAGE_KEY, JSON.stringify(state));
    } catch (e) { console.error(e); }
  }

  function initSavingsChallenges() {
    const state = getChallengeState();

    // 1. 52 Weeks Challenge
    const update52WeeksUI = () => {
      const k = state.fiftyTwoWeeks || 0;
      const savedAmount = 100 * (k * (k + 1)) / 2;
      const nextAmount = (k + 1) * 100;
      const progressPct = Math.min(100, Math.round((k / 52) * 100));

      const savedEl = document.getElementById("chal-52-saved");
      const weekNumEl = document.getElementById("chal-52-week-num");
      const progressEl = document.getElementById("chal-52-progress");
      const nextAmtEl = document.getElementById("chal-52-next-amount");

      if (savedEl) savedEl.textContent = `${formatMoney(savedAmount)} / 137 800 ₽`;
      if (weekNumEl) weekNumEl.textContent = `${k} из 52 недель`;
      if (progressEl) progressEl.style.width = `${progressPct}%`;
      if (nextAmtEl) nextAmtEl.textContent = nextAmount;
    };

    const add52Btn = document.getElementById("btn-chal-52-add");
    const reset52Btn = document.getElementById("btn-chal-52-reset");

    if (add52Btn) {
      add52Btn.addEventListener("click", () => {
        if ((state.fiftyTwoWeeks || 0) < 52) {
          state.fiftyTwoWeeks = (state.fiftyTwoWeeks || 0) + 1;
          saveChallengeState(state);
          update52WeeksUI();
        } else {
          alert("🎉 Поздравляем! Вы завершили челлендж 52 недели!");
        }
      });
    }

    if (reset52Btn) {
      reset52Btn.addEventListener("click", () => {
        if (confirm("Сбросить прогресс челленджа 52 недели?")) {
          state.fiftyTwoWeeks = 0;
          saveChallengeState(state);
          update52WeeksUI();
        }
      });
    }

    update52WeeksUI();

    // 2. 30 Days Coffee/Fastfood free
    const grid30 = document.getElementById("chal-30-grid");

    const update30DaysUI = () => {
      const checkedArr = state.thirtyDays || [];
      const count = checkedArr.length;
      const savedSum = count * 300;
      const progressPct = Math.min(100, Math.round((count / 30) * 100));

      const savedEl = document.getElementById("chal-30-saved");
      const countEl = document.getElementById("chal-30-count");
      const progressEl = document.getElementById("chal-30-progress");

      if (savedEl) savedEl.textContent = `${formatMoney(savedSum)} сэкономлено`;
      if (countEl) countEl.textContent = `${count} / 30 дней`;
      if (progressEl) progressEl.style.width = `${progressPct}%`;

      if (grid30) {
        grid30.innerHTML = "";
        for (let i = 1; i <= 30; i++) {
          const bubble = document.createElement("div");
          const isChecked = checkedArr.includes(i);
          bubble.className = "challenge-bubble" + (isChecked ? " checked" : "");
          bubble.textContent = isChecked ? "✓" : i;

          bubble.addEventListener("click", () => {
            let current = state.thirtyDays || [];
            if (current.includes(i)) {
              current = current.filter(x => x !== i);
            } else {
              current.push(i);
            }
            state.thirtyDays = current;
            saveChallengeState(state);
            update30DaysUI();
          });
          grid30.appendChild(bubble);
        }
      }
    };

    update30DaysUI();

    // 3. Smart Rounding
    const chips = document.querySelectorAll(".rounding-chip");
    const roundEstEl = document.getElementById("chal-round-est");

    const updateRoundingUI = () => {
      const step = state.roundingStep || 100;
      chips.forEach(c => {
        if (Number(c.getAttribute("data-step")) === step) {
          c.classList.add("active");
        } else {
          c.classList.remove("active");
        }
      });

      const estMonthly = step === 10 ? 320 : (step === 50 ? 1600 : 3200);
      if (roundEstEl) roundEstEl.textContent = `~ ${formatMoney(estMonthly)}/мес`;
    };

    chips.forEach(c => {
      c.addEventListener("click", () => {
        state.roundingStep = Number(c.getAttribute("data-step"));
        saveChallengeState(state);
        updateRoundingUI();
      });
    });

    updateRoundingUI();
  }

  // --- Goal Creation Form ---
  const btnShowAddGoal = document.getElementById("btn-show-add-goal");
  const addGoalFormContainer = document.getElementById("add-goal-form-container");
  if (btnShowAddGoal && addGoalFormContainer) {
    btnShowAddGoal.addEventListener("click", () => {
      addGoalFormContainer.style.display = addGoalFormContainer.style.display === "none" ? "block" : "none";
    });
  }

  const btnSaveGoal = document.getElementById("btn-save-goal");
  if (btnSaveGoal) {
    btnSaveGoal.addEventListener("click", async () => {
      const title = document.getElementById("goal-title-input").value.trim();
      const target_amount = parseFloat(document.getElementById("goal-target-input").value) || 0;
      const current_amount = parseFloat(document.getElementById("goal-current-input").value) || 0;
      const months = parseInt(document.getElementById("goal-months-input").value) || null;
      const apy = parseFloat(document.getElementById("goal-apy-input").value) || 0;

      if (!title || target_amount <= 0) {
        alert("Заполните название и целевую сумму накопления");
        return;
      }

      try {
        const headers = { "Content-Type": "application/json" };
        if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

        const res = await fetch("/api/goals", {
          method: "POST",
          headers,
          body: JSON.stringify({ title, target_amount, current_amount, months, apy })
        });

        if (res.ok) {
          alert("✅ Цель добавлена!");
          document.getElementById("goal-title-input").value = "";
          document.getElementById("goal-target-input").value = "";
          document.getElementById("goal-current-input").value = "";
          addGoalFormContainer.style.display = "none";
          loadSummary();
        }
      } catch (e) { console.error(e); }
    });
  }

  // --- Operations Tab Manager ---
  async function loadOperationsTabList() {
    const container = document.getElementById("operations-tab-list");
    if (!container) return;

    try {
      const headers = {};
      if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

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

      // Event listeners for operations tab list
      document.querySelectorAll(".op-delete-btn").forEach(btn => {
        btn.addEventListener("click", async function () {
          const opId = this.getAttribute("data-id");
          if (!confirm("Удалить эту операцию?")) return;

          try {
            const h = {};
            if (tg && tg.initData) h["telegram-web-app-init-data"] = tg.initData;

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
            const h = { "Content-Type": "application/json" };
            if (tg && tg.initData) h["telegram-web-app-init-data"] = tg.initData;

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

  async function loadUserProfile() {
    try {
      const headers = {};
      if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

      const res = await fetch("/api/profile", { headers });
      if (!res.ok) return;

      const prof = await res.json();
      document.getElementById("profile-name").textContent = prof.first_name || "Пользователь";
      document.getElementById("profile-id").textContent = `ID: ${prof.telegram_id}`;
      document.getElementById("profile-income").textContent = "+" + formatMoney(prof.personal_income_month);
      document.getElementById("profile-expense").textContent = "-" + formatMoney(prof.personal_expense_month);
      document.getElementById("profile-savings-rate").textContent = (prof.personal_savings_rate || 0).toFixed(1) + "%";
      document.getElementById("profile-family-share").textContent = (prof.family_share_pct || 0).toFixed(1) + "%";
    } catch (e) { console.error("Profile load error", e); }
  }

  // Check URL Hash for deep linking
  if (window.location.hash === "#subs") {
    const subNavBtn = document.querySelector('.nav-item[data-tab="subs"]');
    if (subNavBtn) subNavBtn.click();
  }

  initFinancialCalendar();
  initCompoundCalculator();
  initSavingsChallenges();

  loadSummary();
  loadTrendsChart();
  loadAuthorsBreakdown();
  loadSubscriptions();
  loadOperationsTabList();
  loadUserProfile();
});

