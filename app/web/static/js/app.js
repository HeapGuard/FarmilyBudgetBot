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

  async function loadSummary() {
    try {
      const headers = {};
      if (tg && tg.initData) {
        headers["telegram-web-app-init-data"] = tg.initData;
      }

      const res = await fetch("/api/summary", { headers });
      if (!res.ok) {
        document.getElementById("content").innerHTML = `<div class="loading">Ошибка загрузки данных (${res.status})</div>`;
        return;
      }

      currentData = await res.json();
      renderApp(currentData);
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
      if (data.financial_runway_months < 3) {
        runwayVal.style.color = "var(--accent-red)";
      } else {
        runwayVal.style.color = "var(--accent-green)";
      }
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
            subText = acc.apy > 0 ? `Ставка ${acc.apy}% • ~+${formatMoney(acc.monthly_interest)}/мес` : "Без процентов";
          } else if (acc.type === "deposit") {
            subText = acc.apy > 0 ? `Ставка ${acc.apy}% на ${acc.months} мес • На выходе ~${formatMoney(acc.projected_total)}` : "Без процента";
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
          passiveItem.style.padding = "4px 8px";
          passiveItem.style.color = "var(--accent-green)";
          passiveItem.style.fontWeight = "600";
          passiveItem.textContent = `💸 Пассивный доход по процентам: ~+${formatMoney(data.total_passive_income_monthly)}/мес`;
          accContainer.appendChild(passiveItem);
        }
      } else {
        accContainer.innerHTML = `<div class="cat-meta" style="padding: 10px;">Нет активных счетов</div>`;
      }
    } else {
      accContainer.innerHTML = `<div class="cat-meta" style="padding: 10px;">Счета не настроены</div>`;
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
      budgetsContainer.innerHTML = `<div class="cat-meta" style="padding: 10px;">Бюджеты категорий не настроены (настройте через /budgets)</div>`;
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
        item.innerHTML = `
          <div class="goal-header">
            <span>🎯 ${goal.title}</span>
            <span>${formatMoney(goal.current_amount)} / ${formatMoney(goal.target_amount)}</span>
          </div>
          <div class="goal-progress-bar">
            <div class="goal-progress-fill" style="width: ${goal.progress_percentage}%"></div>
          </div>
          <div class="goal-meta">
            <span>Прогресс: ${goal.progress_percentage.toFixed(0)}%</span>
            <span>Статус: ${goal.status === 'done' ? 'Достигнута 🎉' : 'В процессе'}</span>
          </div>
        `;
        goalsContainer.appendChild(item);
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

  // Modal setup
  const modal = document.getElementById("accounts-modal");
  const editBtn = document.getElementById("edit-accounts-btn");
  const saveBtn = document.getElementById("save-accounts-btn");
  const cancelBtn = document.getElementById("cancel-accounts-btn");

  if (editBtn && modal) {
    editBtn.addEventListener("click", function() {
      if (currentData && currentData.accounts) {
        const mainAcc = currentData.accounts.find(a => a.type === "main");
        const savAcc = currentData.accounts.find(a => a.type === "savings");
        const depAcc = currentData.accounts.find(a => a.type === "deposit");

        if (mainAcc) document.getElementById("input-main-bal").value = mainAcc.balance;
        if (savAcc) {
          document.getElementById("input-savings-bal").value = savAcc.balance;
          document.getElementById("input-savings-apy").value = savAcc.apy || 0;
          document.getElementById("input-savings-enabled").checked = savAcc.enabled;
        }
        if (depAcc) {
          document.getElementById("input-deposit-bal").value = depAcc.balance;
          document.getElementById("input-deposit-apy").value = depAcc.apy || 0;
          document.getElementById("input-deposit-months").value = depAcc.months || 12;
          document.getElementById("input-deposit-enabled").checked = depAcc.enabled;
        }
      }
      modal.style.display = "flex";
    });
  }

  if (cancelBtn && modal) {
    cancelBtn.addEventListener("click", function() {
      modal.style.display = "none";
    });
  }

  if (saveBtn && modal) {
    saveBtn.addEventListener("click", async function() {
      const payload = {
        main_balance: Number(document.getElementById("input-main-bal").value) || 0,
        savings_balance: Number(document.getElementById("input-savings-bal").value) || 0,
        savings_apy: Number(document.getElementById("input-savings-apy").value) || 0,
        savings_enabled: Boolean(document.getElementById("input-savings-enabled").checked),
        deposit_balance: Number(document.getElementById("input-deposit-bal").value) || 0,
        deposit_apy: Number(document.getElementById("input-deposit-apy").value) || 0,
        deposit_months: Number(document.getElementById("input-deposit-months").value) || 12,
        deposit_enabled: Boolean(document.getElementById("input-deposit-enabled").checked)
      };

      try {
        const headers = { "Content-Type": "application/json" };
        if (tg && tg.initData) {
          headers["telegram-web-app-init-data"] = tg.initData;
        }
        const res = await fetch("/api/accounts", {
          method: "POST",
          headers: headers,
          body: JSON.stringify(payload)
        });
        if (res.ok) {
          modal.style.display = "none";
          loadSummary();
        } else {
          alert("Ошибка сохранения настроек счетов");
        }
      } catch (err) {
        console.error(err);
        alert("Не удалось сохранить счета");
      }
    });
  }

  loadSummary();
});
