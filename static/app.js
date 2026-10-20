/* AI Team Command Center — dashboard behaviour.
 *
 * Talks to the FastAPI backend on the same origin:
 *   POST /api/agents/marketing
 *   POST /api/agents/sales
 *   POST /api/agents/accounting
 *
 * All agent output is inserted with textContent (never innerHTML), so generated
 * copy can never be interpreted as markup.
 */
(function () {
  "use strict";

  var ENDPOINTS = {
    marketing: "/api/agents/marketing",
    sales: "/api/agents/sales",
    accounting: "/api/agents/accounting"
  };

  /* ---------------- DOM helpers ---------------- */

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function responseArea(agent) {
    return document.querySelector('[data-response="' + agent + '"]');
  }

  function money(amount, currency) {
    if (amount === null || amount === undefined) return "—";
    try {
      return new Intl.NumberFormat(undefined, {
        style: "currency",
        currency: currency || "USD"
      }).format(amount);
    } catch (e) {
      return currency + " " + Number(amount).toFixed(2);
    }
  }

  function copyButton(getText) {
    var btn = el("button", "copy", "Copy");
    btn.type = "button";
    btn.addEventListener("click", function () {
      var text = getText();
      var done = function () {
        btn.textContent = "Copied";
        btn.classList.add("is-done");
        setTimeout(function () {
          btn.textContent = "Copy";
          btn.classList.remove("is-done");
        }, 1400);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () {});
      } else {
        var ta = document.createElement("textarea");
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand("copy"); done(); } catch (e) {}
        document.body.removeChild(ta);
      }
    });
    return btn;
  }

  function card(title, rightNode) {
    var wrap = el("section", "card");
    var head = el("div", "card-head");
    head.appendChild(el("h3", null, title));
    if (rightNode) head.appendChild(rightNode);
    wrap.appendChild(head);
    var body = el("div", "card-body");
    wrap.appendChild(body);
    return { card: wrap, body: body };
  }

  function tag(text, kind) {
    return el("span", "tag" + (kind ? " is-" + kind : ""), text);
  }

  /* ---------------- States ---------------- */

  function renderIdle(agent) {
    var area = responseArea(agent);
    clear(area);
    var box = el("div", "empty");
    box.appendChild(el("div", "glyph", "◍"));
    box.appendChild(el("h3", null, "No output yet"));
    box.appendChild(el("p", null, "Fill in the task above and press Run Agent."));
    area.appendChild(box);
  }

  function renderLoading(agent) {
    var area = responseArea(agent);
    clear(area);
    var sk = el("div", "skeleton");
    ["w40", "w80", "w60", "w80", "w40"].forEach(function (w) {
      sk.appendChild(el("div", "line " + w));
    });
    area.appendChild(sk);
  }

  function renderError(agent, status, message) {
    var area = responseArea(agent);
    clear(area);
    var box = el("div", "error");
    box.appendChild(el("h3", null, status ? "Request failed (" + status + ")" : "Request failed"));
    box.appendChild(el("p", null, message || "Unknown error."));
    area.appendChild(box);
  }

  /* ---------------- Renderer: marketing ---------------- */

  function renderMarketing(data, area) {
    clear(area);

    var meta = el("div", "meta-row");
    meta.appendChild(tag(data.detected_category));
    meta.appendChild(tag("Audience: " + data.detected_audience, "muted"));
    meta.appendChild(tag("Tone: " + data.tone, "muted"));
    if (data.keywords && data.keywords.length) {
      meta.appendChild(tag("Keywords: " + data.keywords.slice(0, 5).join(", "), "muted"));
    }
    area.appendChild(meta);

    var posts = card("Social posts (" + data.posts.length + ")");
    data.posts.forEach(function (post) {
      var item = el("div", "item");
      var head = el("div", "item-head");
      var left = el("div");
      left.appendChild(el("div", "name", post.channel));
      left.appendChild(el("div", "sub",
        post.char_count + " / " + post.char_limit + " chars" + (post.truncated ? " · truncated" : "")));
      head.appendChild(left);
      if (post.within_limit) {
        head.appendChild(tag("within limit", "ok"));
      } else {
        head.appendChild(tag("over limit", "crit"));
      }
      item.appendChild(head);

      var body = el("div", "item-body");
      var text = el("pre", "pre", post.post);
      body.appendChild(text);
      var actions = el("div", "card-head");
      actions.style.border = "none";
      actions.style.background = "none";
      actions.style.padding = "10px 0 0";
      actions.appendChild(copyButton(function () { return post.post; }));
      body.appendChild(actions);

      item.appendChild(body);
      posts.body.appendChild(item);
    });
    area.appendChild(posts.card);

    var strategy = card("Strategy points (" + data.strategy.length + ")");
    var list = el("ul", "points");
    data.strategy.forEach(function (s) {
      var li = el("li");
      li.appendChild(el("div", "point", s.point));
      li.appendChild(el("div", "why", s.rationale));
      list.appendChild(li);
    });
    strategy.body.appendChild(list);
    area.appendChild(strategy.card);
  }

  /* ---------------- Renderer: sales ---------------- */

  function renderSales(data, area) {
    clear(area);

    var meta = el("div", "meta-row");
    meta.appendChild(tag(data.detected_industry));
    meta.appendChild(tag("Greeting: Hi " + data.greeting_name + ",", "muted"));
    meta.appendChild(tag("Tone: " + data.tone, "muted"));
    meta.appendChild(tag("Pain: " + data.assumed_pain_point, "muted"));
    area.appendChild(meta);

    var emails = card("Cold outreach emails (" + data.emails.length + ")");
    data.emails.forEach(function (mail) {
      var item = el("div", "item");
      var head = el("div", "item-head");
      var left = el("div");
      left.appendChild(el("div", "name", mail.label));
      left.appendChild(el("div", "sub", mail.word_count + " words · " + mail.recommended_subject));
      head.appendChild(left);
      head.appendChild(copyButton(function () {
        return "Subject: " + mail.recommended_subject + "\n\n" + mail.body;
      }));
      item.appendChild(head);

      var body = el("div", "item-body");

      var subs = el("div");
      subs.appendChild(el("div", "section-title", "Subject lines"));
      var subList = el("ul", "points");
      mail.subject_lines.forEach(function (s) {
        var li = el("li");
        li.appendChild(el("div", "point", s));
        subList.appendChild(li);
      });
      subs.appendChild(subList);
      body.appendChild(subs);

      body.appendChild(el("div", "section-title", "Body"));
      body.appendChild(el("pre", "pre", mail.body));
      item.appendChild(body);
      emails.body.appendChild(item);
    });
    area.appendChild(emails.card);

    var follow = card("Follow-up sequence");
    var tl = el("ul", "tl");
    data.follow_up_sequence.forEach(function (f) {
      var li = el("li");
      li.appendChild(el("div", "when", "Day " + f.day));
      var bodyWrap = el("div");
      bodyWrap.appendChild(el("div", "name", f.purpose + " · " + f.channel));
      bodyWrap.appendChild(el("div", "what", f.message));
      li.appendChild(bodyWrap);
      tl.appendChild(li);
    });
    follow.body.appendChild(tl);
    area.appendChild(follow.card);

    var notes = card("Targeting notes");
    var nlist = el("ul", "points");
    data.targeting_notes.forEach(function (n) {
      var li = el("li");
      li.appendChild(el("div", "point", n.point));
      li.appendChild(el("div", "why", n.rationale));
      nlist.appendChild(li);
    });
    notes.body.appendChild(nlist);
    area.appendChild(notes.card);
  }

  /* ---------------- Renderer: accounting ---------------- */

  function statBlock(label, value, kind) {
    var box = el("div", "stat");
    box.appendChild(el("div", "label", label));
    box.appendChild(el("div", "value" + (kind ? " is-" + kind : ""), value));
    return box;
  }

  function barRows(rows, kind) {
    var wrap = el("div", "bars");
    rows.forEach(function (r) {
      var row = el("div", "bar-row");
      var label = el("div", "bar-label");
      label.appendChild(el("span", null, r.category));
      var amt = el("span", "amt", money(r.amount));
      amt.appendChild(el("span", null, r.share_pct + "%"));
      label.appendChild(amt);
      row.appendChild(label);

      var track = el("div", "track");
      var fill = el("div", "fill" + (kind === "income" ? " is-income" : ""));
      var pct = Math.max(2, Math.min(100, r.share_pct));
      fill.style.width = pct + "%";
      track.appendChild(fill);
      row.appendChild(track);
      wrap.appendChild(row);
    });
    return wrap;
  }

  function renderAccounting(data, area) {
    clear(area);

    var statusKind = data.status === "critical" ? "crit"
      : data.status === "needs_attention" ? "warn" : "ok";
    var statusLabel = data.status === "needs_attention" ? "Needs attention" : data.status;

    var summary = card("Financial status");
    summary.body.appendChild(tag(statusLabel, statusKind));
    summary.body.firstChild.style.marginBottom = "13px";

    var t = data.totals;
    var stats = el("div", "stats");
    stats.appendChild(statBlock("Total income", money(t.total_income, data.currency), "ok"));
    stats.appendChild(statBlock("Total expenses", money(t.total_expenses, data.currency)));
    stats.appendChild(statBlock("Net", money(t.net, data.currency),
      t.net < 0 ? "crit" : (t.net > 0 ? "ok" : null)));
    stats.appendChild(statBlock("Closing balance", money(t.closing_balance, data.currency)));
    stats.appendChild(statBlock("Profit margin",
      t.profit_margin_pct === null ? "—" : t.profit_margin_pct + "%",
      t.profit_margin_pct === null ? null : (t.profit_margin_pct < 0 ? "crit" : null)));
    summary.body.appendChild(stats);
    area.appendChild(summary.card);

    var income = card("Income by category");
    if (data.income_by_category.length) {
      income.body.appendChild(barRows(data.income_by_category, "income"));
    } else {
      income.body.appendChild(el("p", "mono", "No income recorded."));
    }
    area.appendChild(income.card);

    var expenses = card("Expenses by category");
    if (data.expenses_by_category.length) {
      expenses.body.appendChild(barRows(data.expenses_by_category));
    } else {
      expenses.body.appendChild(el("p", "mono", "No expenses recorded."));
    }
    area.appendChild(expenses.card);

    if (data.monthly_totals) {
      var monthly = card("Monthly breakdown");
      var mrows = el("div", "bars");
      Object.keys(data.monthly_totals).forEach(function (month) {
        var m = data.monthly_totals[month];
        var row = el("div", "bar-row");
        var label = el("div", "bar-label");
        label.appendChild(el("span", null, month));
        var amt = el("span", "amt", money(m.net, data.currency));
        amt.appendChild(el("span", null,
          money(m.income, data.currency) + " in / " + money(m.expenses, data.currency) + " out"));
        label.appendChild(amt);
        row.appendChild(label);
        mrows.appendChild(row);
      });
      monthly.body.appendChild(mrows);
      area.appendChild(monthly.card);
    }

    if (data.top_expenses && data.top_expenses.length) {
      var top = card("Largest expenses");
      var list = el("ul", "points");
      data.top_expenses.forEach(function (e) {
        var li = el("li");
        var head = el("div", "point", e.category + " — " + money(e.amount, data.currency));
        var why = el("div", "why",
          (e.description ? e.description + (e.date ? " · " : "") : "") + (e.date || "no date"));
        li.appendChild(head);
        li.appendChild(why);
        list.appendChild(li);
      });
      top.body.appendChild(list);
      area.appendChild(top.card);
    }

    var alerts = card("Alerts (" + data.alerts.length + ")");
    var alist = el("ul", "alerts");
    data.alerts.forEach(function (a) {
      var li = el("li", "is-" + a.level);
      li.appendChild(el("span", "lvl", a.level));
      li.appendChild(el("span", null, a.message));
      alist.appendChild(li);
    });
    alerts.body.appendChild(alist);
    area.appendChild(alerts.card);
  }

  var RENDERERS = {
    marketing: renderMarketing,
    sales: renderSales,
    accounting: renderAccounting
  };

  /* ---------------- Payload builders ---------------- */

  function buildMarketingPayload() {
    var text = document.getElementById("prompt-marketing").value.trim();
    if (!text) throw new Error("Describe the product you want to market first.");
    var payload = { product_description: text };
    var name = document.getElementById("marketing-name").value.trim();
    if (name) payload.product_name = name;
    var brand = document.getElementById("marketing-brand").value.trim();
    if (brand) payload.brand = brand;
    payload.tone = document.getElementById("marketing-tone").value;
    return payload;
  }

  function buildSalesPayload() {
    var text = document.getElementById("prompt-sales").value.trim();
    if (!text) throw new Error("Name the customer type you want to sell to first.");
    var payload = { target_customer_type: text };
    var name = document.getElementById("sales-name").value.trim();
    if (name) payload.product_name = name;
    payload.tone = document.getElementById("sales-tone").value;
    payload.variants = parseInt(document.getElementById("sales-variants").value, 10);
    return payload;
  }

  // Accounting accepts either pasted JSON or plain "type, category, amount[, date]" lines.
  function buildAccountingPayload() {
    var raw = document.getElementById("prompt-accounting").value.trim();
    if (!raw) throw new Error("Add at least one income or expense line.");

    var payload;
    if (raw.charAt(0) === "[" || raw.charAt(0) === "{") {
      try {
        var parsed = JSON.parse(raw);
      } catch (e) {
        throw new Error("That JSON could not be parsed: " + e.message);
      }
      payload = Array.isArray(parsed) ? { entries: parsed } : parsed;
      if (!payload.entries) throw new Error("JSON must be an array of entries, or an object with an 'entries' array.");
    } else {
      var entries = [];
      raw.split("\n").forEach(function (line) {
        var text = line.trim();
        if (!text || text.charAt(0) === "#") return;
        var parts = text.split(/[,\t]/).map(function (p) { return p.trim(); });
        if (parts.length < 3 || !parts[0] || !parts[1] || !parts[2]) {
          throw new Error('Line "' + text + '" needs: type, category, amount (date optional).');
        }
        var amount = Number(parts[2]);
        if (!isFinite(amount)) throw new Error('Line "' + text + '" has a non-numeric amount.');
        var entry = { type: parts[0].toLowerCase(), category: parts[1], amount: amount };
        if (parts[3]) entry.date = parts[3];
        entries.push(entry);
      });
      if (!entries.length) throw new Error("Add at least one income or expense line.");
      payload = { entries: entries };
    }

    payload.opening_balance = parseFloat(document.getElementById("accounting-opening").value) || 0;
    var currency = document.getElementById("accounting-currency").value.trim();
    if (currency) payload.currency = currency.toUpperCase();
    return payload;
  }

  var BUILDERS = {
    marketing: buildMarketingPayload,
    sales: buildSalesPayload,
    accounting: buildAccountingPayload
  };

  /* ---------------- Run ---------------- */

  function setBusy(agent, busy) {
    var btn = document.querySelector('[data-run="' + agent + '"]');
    if (!btn) return;
    btn.disabled = busy;
    var label = btn.querySelector(".run-label");
    var spinner = btn.querySelector(".spinner");
    if (busy) {
      label.textContent = "Running…";
      if (!spinner) btn.insertBefore(el("span", "spinner"), label);
    } else {
      label.textContent = "Run Agent";
      if (spinner) btn.removeChild(spinner);
    }
  }

  async function runAgent(agent) {
    var payload;
    try {
      payload = BUILDERS[agent]();
    } catch (e) {
      renderError(agent, null, e.message);
      return;
    }

    setBusy(agent, true);
    renderLoading(agent);

    try {
      var res = await fetch(ENDPOINTS[agent], {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      var text = await res.text();
      var data = null;
      try { data = JSON.parse(text); } catch (e) { /* handled below */ }

      if (!res.ok) {
        var msg = "The server rejected the request.";
        if (data && data.detail) {
          msg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
        } else if (text) {
          msg = text.slice(0, 300);
        }
        renderError(agent, res.status, msg);
        return;
      }

      if (!data) {
        renderError(agent, res.status, "The server returned a response that could not be parsed.");
        return;
      }

      RENDERERS[agent](data, responseArea(agent));
    } catch (e) {
      renderError(agent, null, "Could not reach the backend. Is the server running? (" + e.message + ")");
    } finally {
      setBusy(agent, false);
    }
  }

  /* ---------------- Tabs ---------------- */

  function selectTab(agent, focus) {
    document.querySelectorAll(".nav-item").forEach(function (btn) {
      var on = btn.dataset.panel === agent;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
      btn.tabIndex = on ? 0 : -1;
      if (on && focus) btn.focus();
    });
    document.querySelectorAll(".panel").forEach(function (panel) {
      var on = panel.id === "panel-" + agent;
      panel.classList.toggle("is-active", on);
      panel.hidden = !on;
    });
    try { history.replaceState(null, "", "#" + agent); } catch (e) {}
  }

  function wireTabs() {
    var tabs = Array.prototype.slice.call(document.querySelectorAll(".nav-item"));

    tabs.forEach(function (btn, index) {
      btn.addEventListener("click", function () { selectTab(btn.dataset.panel, false); });

      btn.addEventListener("keydown", function (event) {
        var next = null;
        if (event.key === "ArrowDown" || event.key === "ArrowRight") {
          next = tabs[(index + 1) % tabs.length];
        } else if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
          next = tabs[(index - 1 + tabs.length) % tabs.length];
        } else if (event.key === "Home") {
          next = tabs[0];
        } else if (event.key === "End") {
          next = tabs[tabs.length - 1];
        }
        if (next) {
          event.preventDefault();
          selectTab(next.dataset.panel, true);
        }
      });
    });
  }

  /* ---------------- Wiring ---------------- */

  function wireRunners() {
    document.querySelectorAll("[data-run]").forEach(function (btn) {
      btn.addEventListener("click", function () { runAgent(btn.dataset.run); });
    });

    document.querySelectorAll(".composer textarea").forEach(function (area) {
      area.addEventListener("keydown", function (event) {
        if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
          event.preventDefault();
          var panel = area.closest(".panel");
          if (panel) {
            var btn = panel.querySelector("[data-run]");
            if (btn) runAgent(btn.dataset.run);
          }
        }
      });
    });
  }

  function checkHealth() {
    var dot = document.querySelector("#health .dot");
    var text = document.getElementById("health-text");
    fetch("/health")
      .then(function (res) { return res.json(); })
      .then(function (data) {
        dot.classList.add("is-ok");
        text.textContent = "Backend online · " + data.agents + " agents";
      })
      .catch(function () {
        dot.classList.add("is-down");
        text.textContent = "Backend unreachable";
      });
  }

  function init() {
    Object.keys(RENDERERS).forEach(renderIdle);
    wireTabs();
    wireRunners();
    checkHealth();

    var hash = (window.location.hash || "").replace("#", "");
    if (hash && RENDERERS[hash]) selectTab(hash, false);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();