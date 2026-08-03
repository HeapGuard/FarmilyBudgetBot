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
    item.addEventListener("click", function() {
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
        btn.addEventListener("click", async function() {
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
        btn.addEventListener("click", async function() {
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
    btn.addEventListener("click", function() {
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
    submitOpBtn.addEventListener("click", async function() {
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
    qrFileInput.addEventListener("change", async function() {
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
    saveAccTabBtn.addEventListener("click", async function() {
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
    saveBudgetBtn.addEventListener("click", async function() {
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

  // --- Subscriptions Tab ---
  async function loadSubscriptions() {
    const container = document.getElementById("subs-list");
    if (!container) return;

    try {
      const headers = {};
      if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

      const res = await fetch("/api/subscriptions", { headers });
      if (!res.ok) return;

      const data = await res.json();
      document.getElementById("subs-total-monthly").textContent = formatMoney(data.total_monthly);
      document.getElementById("subs-total-yearly").textContent = formatMoney(data.total_yearly);

      // Render interactive calendar
      renderSubCalendar(data.subscriptions);

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
        btn.addEventListener("click", async function() {
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
        btn.addEventListener("click", async function() {
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
        btn.addEventListener("click", async function() {
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

  // --- Interactive Subscriptions Calendar ---
  function renderSubCalendar(subscriptions) {
    const grid = document.getElementById("calendar-days-grid");
    if (!grid) return;
    grid.innerHTML = "";

    const now = new Date();
    const currentYear = now.getFullYear();
    const currentMonth = now.getMonth();

    const monthNames = [
      "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
      "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ];
    document.getElementById("calendar-month-name").textContent = `${monthNames[currentMonth]} ${currentYear}`;

    const firstDay = new Date(currentYear, currentMonth, 1).getDay();
    const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
    const startOffset = firstDay === 0 ? 6 : firstDay - 1;

    const subMap = {};
    if (subscriptions) {
      subscriptions.forEach(sub => {
        const day = sub.billing_day;
        if (!subMap[day]) subMap[day] = [];
        subMap[day].push(sub);
      });
    }

    for (let i = 0; i < startOffset; i++) {
      const emptyCell = document.createElement("div");
      emptyCell.className = "calendar-day empty";
      grid.appendChild(emptyCell);
    }

    for (let day = 1; day <= daysInMonth; day++) {
      const dayCell = document.createElement("div");
      dayCell.className = "calendar-day";
      dayCell.textContent = day;

      if (subMap[day]) {
        dayCell.classList.add("has-sub");
      }

      if (day === now.getDate()) {
        dayCell.style.border = "1.5px solid var(--accent-blue)";
      }

      dayCell.addEventListener("click", function() {
        document.querySelectorAll(".calendar-day").forEach(c => c.classList.remove("selected"));
        dayCell.classList.add("selected");

        const detailsEl = document.getElementById("calendar-day-details");
        const titleEl = document.getElementById("calendar-details-title");
        const listEl = document.getElementById("calendar-details-list");

        if (subMap[day]) {
          detailsEl.style.display = "block";
          const declMonth = monthNames[currentMonth].toLowerCase().replace(/ь$/, 'я').replace(/т$/, 'та').replace(/й$/, 'я');
          titleEl.textContent = `Списания ${day} ${declMonth}:`;
          listEl.innerHTML = subMap[day].map(sub => `
            <div style="display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.03);">
              <span>🔔 ${sub.name}</span>
              <strong style="color: var(--accent-red);">${formatMoney(sub.amount)}</strong>
            </div>
          `).join("");
        } else {
          detailsEl.style.display = "block";
          const declMonth = monthNames[currentMonth].toLowerCase().replace(/ь$/, 'я').replace(/т$/, 'та').replace(/й$/, 'я');
          titleEl.textContent = `Списания ${day} ${declMonth}:`;
          listEl.innerHTML = `<span style="color: var(--text-muted);">В этот день списаний нет 👍</span>`;
        }
      });

      grid.appendChild(dayCell);
    }
  }

  // --- Interactive Compound Interest Goal Planner ---
  let plannerChartInstance = null;

  function initGoalPlanner() {
    const inputStart = document.getElementById("planner-start-sum");
    const inputMonthly = document.getElementById("planner-monthly-dep");
    const inputMonths = document.getElementById("planner-months");
    const inputApy = document.getElementById("planner-apy");

    if (!inputStart) return;

    const updateCalc = () => {
      const startVal = parseFloat(inputStart.value);
      const monthlyVal = parseFloat(inputMonthly.value);
      const monthsVal = parseInt(inputMonths.value);
      const apyVal = parseFloat(inputApy.value) / 100;

      document.getElementById("lbl-planner-start").textContent = startVal.toLocaleString("ru-RU") + " ₽";
      document.getElementById("lbl-planner-monthly").textContent = monthlyVal.toLocaleString("ru-RU") + " ₽";
      document.getElementById("lbl-planner-months").textContent = `${monthsVal} месяцев`;
      document.getElementById("lbl-planner-apy").textContent = `${inputApy.value}%`;

      let totalContributions = startVal;
      let balance = startVal;
      let totalInterest = 0;

      const labels = [];
      const contributionsData = [];
      const interestData = [];

      labels.push("Старт");
      contributionsData.push(startVal);
      interestData.push(0);

      const r = apyVal / 12;

      for (let m = 1; m <= monthsVal; m++) {
        const interestPaid = balance * r;
        totalInterest += interestPaid;
        totalContributions += monthlyVal;
        balance = balance + interestPaid + monthlyVal;

        labels.push(`${m} мес`);
        contributionsData.push(Math.round(totalContributions));
        interestData.push(Math.round(totalInterest));
      }

      document.getElementById("planner-total-result").textContent = Math.round(balance).toLocaleString("ru-RU") + " ₽";
      document.getElementById("planner-interest-share").textContent = `Свои взносы: ${Math.round(totalContributions).toLocaleString("ru-RU")} ₽ • Проценты: ${Math.round(totalInterest).toLocaleString("ru-RU")} ₽`;

      const canvas = document.getElementById("goal-calc-chart");
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (plannerChartInstance) plannerChartInstance.destroy();

      plannerChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: labels,
          datasets: [
            {
              label: 'Свои взносы',
              data: contributionsData,
              backgroundColor: 'rgba(59, 130, 246, 0.65)',
              borderColor: 'var(--accent-blue)',
              borderWidth: 1
            },
            {
              label: 'Начисленные проценты',
              data: interestData,
              backgroundColor: 'rgba(16, 185, 129, 0.65)',
              borderColor: 'var(--accent-green)',
              borderWidth: 1
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              display: true,
              labels: { color: '#94a3b8', boxWidth: 10, font: { size: 8 } }
            }
          },
          scales: {
            x: {
              stacked: true,
              ticks: { color: '#94a3b8', font: { size: 8 } },
              grid: { display: false }
            },
            y: {
              stacked: true,
              ticks: { color: '#94a3b8', font: { size: 8 } },
              grid: { color: 'rgba(255,255,255,0.05)' }
            }
          }
        }
      });
    };

    [inputStart, inputMonthly, inputMonths, inputApy].forEach(input => {
      input.addEventListener("input", updateCalc);
    });

    updateCalc();
  }

  // --- Gamified Savings Challenges ---
  function initSavingsChallenges() {
    // Challenge 1: 52 Weeks
    let w52Progress = parseInt(localStorage.getItem("challenge_52w_week")) || 0;

    const update52wUI = () => {
      const nextSum = (w52Progress + 1) * 100;
      const totalAccumulated = w52Progress * (100 + (w52Progress * 100)) / 2;
      const pct = Math.min(100, Math.round((w52Progress / 52) * 100));

      document.getElementById("lbl-challenge-52w-progress").textContent = `Неделя ${w52Progress} из 52`;
      document.getElementById("lbl-challenge-52w-next-sum").textContent = nextSum.toLocaleString("ru-RU") + " ₽";
      document.getElementById("lbl-challenge-52w-total").textContent = totalAccumulated.toLocaleString("ru-RU") + " ₽";
      document.getElementById("challenge-52w-progress-fill").style.width = `${pct}%`;

      if (w52Progress >= 52) {
        document.getElementById("lbl-challenge-52w-next-sum").textContent = "Выполнено! 🎉";
        document.getElementById("btn-challenge-52w-check").style.display = "none";
      }
    };

    const btn52w = document.getElementById("btn-challenge-52w-check");
    if (btn52w) {
      btn52w.addEventListener("click", () => {
        if (w52Progress < 52) {
          w52Progress += 1;
          localStorage.setItem("challenge_52w_week", w52Progress);
          update52wUI();
          alert("🎉 Отлично! Взнос этой недели выполнен и отложен в копилку!");
        }
      });
    }
    update52wUI();

    // Challenge 2: 30 Days Habit
    const habitGrid = document.getElementById("challenge-habit-grid");
    if (habitGrid) {
      let checkedDays = [];
      try {
        checkedDays = JSON.parse(localStorage.getItem("challenge_habit_days")) || [];
      } catch (e) { checkedDays = []; }

      const renderHabitGrid = () => {
        habitGrid.innerHTML = "";
        const savedMoney = checkedDays.length * 250;
        document.getElementById("lbl-challenge-habit-saved").textContent = `Сэкономлено: ${savedMoney.toLocaleString("ru-RU")} ₽`;

        for (let i = 1; i <= 30; i++) {
          const bubble = document.createElement("div");
          bubble.className = "challenge-bubble";
          bubble.textContent = i;

          if (checkedDays.includes(i)) {
            bubble.classList.add("checked");
          }

          bubble.addEventListener("click", () => {
            if (checkedDays.includes(i)) {
              checkedDays = checkedDays.filter(d => d !== i);
            } else {
              checkedDays.push(i);
            }
            localStorage.setItem("challenge_habit_days", JSON.stringify(checkedDays));
            renderHabitGrid();
          });

          habitGrid.appendChild(bubble);
        }
      };
      renderHabitGrid();
    }

    // Feature 3: Coin Jar Select Rounding
    const jarSelect = document.getElementById("coinjar-round-select");
    const jarProj = document.getElementById("lbl-coinjar-projection");
    if (jarSelect && jarProj) {
      const updateJarProj = () => {
        const roundLevel = parseInt(jarSelect.value);
        let projection = 14500;
        if (roundLevel === 10) projection = 3200;
        else if (roundLevel === 100) projection = 34500;

        jarProj.textContent = `~${projection.toLocaleString("ru-RU")} ₽ / год`;
      };
      jarSelect.addEventListener("change", updateJarProj);
      updateJarProj();
    }
  }

  loadSummary();
  loadTrendsChart();
  loadAuthorsBreakdown();
  loadSubscriptions();
  loadOperationsTabList();
  loadUserProfile();
  initGoalPlanner();
  initSavingsChallenges();
});
