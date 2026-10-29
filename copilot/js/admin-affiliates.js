(() => {
  'use strict';
  const list = document.getElementById('affiliateList');
  const detail = document.getElementById('affiliateDetail');
  const status = document.getElementById('affiliateStatus');
  const createForm = document.getElementById('affiliateCreate');
  let currentPage = 1;
  let selected = null;
  let referralPage = 1;
  let selectionVersion = 0;
  const path = id => `/admin/affiliates/${encodeURIComponent(id)}`;
  const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const text = value => escapeHtml(value);
  const date = value => value ? new Date(value).toLocaleDateString('pt-BR') : 'Não informado';
  const field = (name, label, value = '', type = 'text', extra = '') => `<label>${label}<input class="control" name="${name}" type="${type}" value="${text(value)}" ${extra}></label>`;

  function formFields(partner = {}) {
    return `<div class="filters">
      ${field('name', 'Nome ', partner.name || '', 'text', 'required maxlength="120"')}
      ${field('public_name', 'Nome público ', partner.public_name || '', 'text', 'required maxlength="120"')}
      ${field('email', 'E-mail de contato ', partner.email || '', 'email')}
      ${field('user_id', 'Conta vinculada (UUID) ', partner.user_id || '')}
      ${!partner.id ? field('code', 'Código (vazio: gerar) ', '', 'text', 'maxlength="32"') : ''}
      ${field('first_rate', 'Primeira cobrança mensal (%) ', partner.first_rate ?? 50, 'number', 'required min="0" max="100" step="0.01"')}
      ${field('renewal_rate', 'Renovações mensais (%) ', partner.renewal_rate ?? 10, 'number', 'required min="0" max="100" step="0.01"')}
      ${field('recurring_months', 'Recorrência (meses) ', partner.recurring_months ?? 12, 'number', 'required min="0" step="1"')}
      ${field('annual_first_rate', 'Primeira cobrança anual (%) — vazio: sem regra ', partner.annual_first_rate ?? '', 'number', 'min="0" max="100" step="0.01"')}
      ${field('annual_renewal_rate', 'Renovações anuais (%) — vazio: sem regra ', partner.annual_renewal_rate ?? '', 'number', 'min="0" max="100" step="0.01"')}
      <label>Observações <textarea class="control" name="notes">${text(partner.notes || '')}</textarea></label>
      <label><input name="active" type="checkbox" ${partner.active !== false ? 'checked' : ''}> Parceria ativa</label>
    </div><div><button class="action primary" type="submit">${partner.id ? 'Salvar alterações' : 'Cadastrar influencer'}</button></div>`;
  }

  function readForm(form) {
    const data = Object.fromEntries(new FormData(form));
    for (const key of ['first_rate', 'renewal_rate', 'recurring_months']) data[key] = Number(data[key]);
    for (const key of ['annual_first_rate', 'annual_renewal_rate']) data[key] = data[key] === '' ? null : Number(data[key]);
    data.active = form.elements.active.checked;
    data.user_id = data.user_id.trim() || null;
    data.email = data.email.trim() || null;
    if ('code' in data) data.code = data.code.trim().toUpperCase() || undefined;
    return data;
  }

  function paginate(container, page, pages, onPage) {
    container.replaceChildren();
    for (const [label, next, disabled] of [['Anterior', page - 1, page <= 1], ['Próxima', page + 1, page >= pages]]) {
      const button = document.createElement('button');
      button.className = 'action small';
      button.textContent = label;
      button.disabled = disabled;
      button.addEventListener('click', () => runAdminAction(button, () => onPage(next)));
      container.append(button);
      if (label === 'Anterior') {
        const count = document.createElement('span');
        count.textContent = `Página ${page} de ${Math.max(1, pages)}`;
        container.append(count);
      }
    }
  }

  async function load(page = currentPage) {
    status.textContent = 'Carregando parceiros…';
    try {
      const data = await api(`/admin/affiliates?page=${page}&per_page=50`);
      currentPage = data.page;
      list.replaceChildren();
      for (const partner of data.affiliates) {
        const row = document.createElement('div');
        row.className = 'item';
        const name = document.createElement('span');
        name.textContent = `${partner.public_name || partner.name} · ${partner.active ? 'Ativa' : 'Inativa'} · ${partner.metrics.registrations} cadastros`;
        const button = document.createElement('button');
        button.className = 'action small';
        button.textContent = 'Ver e editar';
        button.addEventListener('click', () => runAdminAction(button, () => selectPartner(partner)));
        row.append(name, button);
        list.append(row);
      }
      status.textContent = data.total ? `${data.total} parceiro(s)` : 'Nenhum parceiro cadastrado.';
      paginate(document.getElementById('affiliatePagination'), data.page, data.pages, load);
      if (selected) {
        const fresh = data.affiliates.find(item => item.id === selected.id);
        if (fresh) await selectPartner(fresh, referralPage);
      }
    } catch (error) {
      status.textContent = error.message || 'Falha ao carregar parceiros.';
      throw error;
    }
  }

  function metric(label, value) {
    return `<div class="mini"><div class="k">${label}</div><div class="v">${value == null ? 'Sem confirmação' : text(value)}</div></div>`;
  }

  async function selectPartner(partner, page = 1) {
    selected = partner;
    referralPage = page;
    const version = ++selectionVersion;
    detail.hidden = false;
    const metrics = partner.metrics || {};
    detail.innerHTML = `<h3>${text(partner.public_name || partner.name)}</h3>
      <div class="mini-stats">
        ${metric('Cadastros atribuídos', metrics.registrations)}
        ${metric('Pagantes confirmados', metrics.confirmed_paying_users)}
        ${metric('Acessos de assinatura ativos', metrics.active_subscribers)}
        ${metric('Cancelamentos registrados', metrics.cancellations)}
      </div>
      <p class="muted">Financeiro desativado: comissões pendentes e liberadas indisponíveis. Ausência de confirmação de compra não significa ausência de assinaturas.</p>
      <details style="margin-top:14px;"><summary>Editar parceria e regras de comissão</summary><form id="affiliateEdit" class="grid" style="margin-top:14px;">${formFields(partner)}</form></details>
      <h4>Códigos e histórico</h4><div id="affiliateCodes" class="list"></div>
      <form id="affiliateCodeCreate" class="filters" style="margin-top:14px;"><label>Novo código (vazio: gerar) <input name="code" maxlength="32"></label><button class="action" type="submit">Criar código</button></form>
      <h4>Usuários indicados</h4><p id="affiliateReferralsStatus" role="status">Carregando indicações…</p>
      <div class="table-wrap"><table><thead><tr><th>Usuário</th><th>ID</th><th>Atribuição</th><th>Código</th><th>Compra confirmada</th><th>Assinatura</th></tr></thead><tbody id="affiliateReferrals"></tbody></table></div>
      <div class="pagination" id="affiliateReferralsPagination"></div>
      <h4>Histórico de pagamentos</h4><p id="affiliatePayouts">Carregando registros…</p>`;
    renderCodes(partner);
    document.getElementById('affiliateEdit').addEventListener('submit', event => {
      event.preventDefault();
      const form = event.currentTarget;
      runAdminAction(form.querySelector('[type=submit]'), async () => {
        await api(path(partner.id), json('PATCH', readForm(form)));
        showToast('Parceria atualizada');
        await load();
      });
    });
    document.getElementById('affiliateCodeCreate').addEventListener('submit', event => {
      event.preventDefault();
      const form = event.currentTarget;
      runAdminAction(form.querySelector('[type=submit]'), async () => {
        const code = form.elements.code.value.trim().toUpperCase();
        await api(`${path(partner.id)}/codes`, json('POST', code ? { code } : {}));
        showToast('Código criado');
        await load();
      });
    });
    const results = await Promise.allSettled([
      api(`${path(partner.id)}/referrals?page=${page}`),
      api(`${path(partner.id)}/payouts`)
    ]);
    if (version !== selectionVersion) return;
    const [referrals, payouts] = results;
    const referralStatus = document.getElementById('affiliateReferralsStatus');
    if (referrals.status === 'fulfilled') {
      const data = referrals.value;
      referralStatus.textContent = `${data.total} indicação(ões)`;
      const rows = document.getElementById('affiliateReferrals');
      for (const user of data.referrals) {
        const row = document.createElement('tr');
        for (const value of [user.username, user.user_id, date(user.created_at), user.code, user.paid_confirmed ? 'Sim' : 'Sem confirmação', user.subscription_status || 'Sem confirmação']) {
          const cell = document.createElement('td');
          cell.textContent = value ?? 'Não informado';
          row.append(cell);
        }
        rows.append(row);
      }
      paginate(document.getElementById('affiliateReferralsPagination'), data.page, data.pages, next => selectPartner(partner, next));
    } else referralStatus.textContent = referrals.reason.message || 'Falha ao carregar indicações.';
    const payoutStatus = document.getElementById('affiliatePayouts');
    if (payouts.status === 'fulfilled') {
      payoutStatus.textContent = payouts.value.payouts.length ? `${payouts.value.payouts.length} registro(s) de pagamento.` : 'Nenhum pagamento registrado. Operação financeira desativada.';
    } else payoutStatus.textContent = payouts.reason.message || 'Falha ao carregar pagamentos.';
  }

  function renderCodes(partner) {
    const codes = document.getElementById('affiliateCodes');
    for (const code of partner.codes || []) {
      const row = document.createElement('div');
      row.className = 'item';
      const label = document.createElement('span');
      label.textContent = `${code.code} · ${code.active ? 'Ativo' : 'Desativado'} · ${date(code.created_at)}`;
      const actions = document.createElement('div');
      actions.className = 'row-actions';
      const copy = document.createElement('button');
      copy.className = 'action small';
      copy.textContent = 'Copiar';
      copy.addEventListener('click', () => runAdminAction(copy, async () => {
        await navigator.clipboard.writeText(code.code);
        showToast('Código copiado');
      }));
      actions.append(copy);
      if (code.active) {
        const disable = document.createElement('button');
        disable.className = 'action small';
        disable.textContent = 'Desativar';
        disable.addEventListener('click', () => runAdminAction(disable, async () => {
          await api(`${path(partner.id)}/codes/${encodeURIComponent(code.code)}`, json('PATCH', { active: false }));
          showToast('Código desativado; histórico preservado');
          await load();
        }));
        actions.append(disable);
      }
      row.append(label, actions);
      codes.append(row);
    }
    if (!partner.codes?.length) codes.textContent = 'Nenhum código cadastrado.';
  }

  createForm.innerHTML = formFields();
  createForm.addEventListener('submit', event => {
    event.preventDefault();
    runAdminAction(createForm.querySelector('[type=submit]'), async () => {
      const partner = await api('/admin/affiliates', json('POST', readForm(createForm)));
      createForm.reset();
      showToast('Influencer cadastrada');
      await load(1);
      await selectPartner(partner);
    });
  });
  document.getElementById('adminTabAffiliates').addEventListener('click', () => load().catch(error => showToast(error.message)));
  window.adminAffiliates = { load };
})();
