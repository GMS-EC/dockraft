// Dockraft Webhooks Management Script
const Webhooks = {
  config: null,
  currentModalChannel: null,
  isTesting: false,

  async loadConfig() {
    try {
      const res = await fetch('/api/webhooks/config');
      if (!res.ok) throw new Error("Error al obtener configuración de webhooks");
      this.config = await res.json();
      this.populateUI(this.config);
    } catch (err) {
      console.error("[Webhooks]", err);
      App.showToast(err.message, 'danger');
    }
  },

  populateUI(cfg) {
    if (!cfg) return;

    // Discord
    const discord = cfg.discord || {};
    const dEn = document.getElementById('webhook-discord-enable');
    const dUrl = document.getElementById('webhook-discord-url');
    if (dEn) dEn.checked = !!discord.enabled;
    if (dUrl) dUrl.value = discord.webhook_url || '';

    // Telegram
    const tg = cfg.telegram || {};
    const tgEn = document.getElementById('webhook-telegram-enable');
    const tgTok = document.getElementById('webhook-telegram-token');
    const tgChat = document.getElementById('webhook-telegram-chatid');
    if (tgEn) tgEn.checked = !!tg.enabled;
    if (tgTok) tgTok.value = tg.bot_token || '';
    if (tgChat) tgChat.value = tg.chat_id || '';

    // Email
    const em = cfg.email || {};
    const emEn = document.getElementById('webhook-email-enable');
    const emHost = document.getElementById('webhook-email-host');
    const emPort = document.getElementById('webhook-email-port');
    const emUser = document.getElementById('webhook-email-user');
    const emPass = document.getElementById('webhook-email-pass');
    const emTls = document.getElementById('webhook-email-tls');
    const emFrom = document.getElementById('webhook-email-from');
    const emTo = document.getElementById('webhook-email-to');
    if (emEn) emEn.checked = !!em.enabled;
    if (emHost) emHost.value = em.smtp_host || '';
    if (emPort) emPort.value = em.smtp_port || 587;
    if (emUser) emUser.value = em.smtp_user || '';
    if (emPass) emPass.value = em.smtp_password || '';
    if (emTls) emTls.checked = em.smtp_use_tls !== false;
    if (emFrom) emFrom.value = em.from_email || '';
    if (emTo) emTo.value = em.to_emails || '';

    // Events
    const ev = cfg.events || {};
    const evStart = document.getElementById('webhook-event-start');
    const evStop = document.getElementById('webhook-event-stop');
    const evCrash = document.getElementById('webhook-event-crash');
    const evBackup = document.getElementById('webhook-event-backup');
    const evTask = document.getElementById('webhook-event-task');
    const evPlayer = document.getElementById('webhook-event-player');

    if (evStart) evStart.checked = ev.server_start !== false;
    if (evStop) evStop.checked = ev.server_stop !== false;
    if (evCrash) evCrash.checked = ev.server_crash !== false;
    if (evBackup) evBackup.checked = ev.backup_created !== false;
    if (evTask) evTask.checked = ev.task_executed !== false;
    if (evPlayer) evPlayer.checked = !!ev.player_join;

    this.updateStatusBadges();
  },

  updateStatusBadges() {
    if (!this.config) return;

    // Discord Status
    const dUrl = (this.config.discord?.webhook_url || '').trim();
    const dBadge = document.getElementById('webhook-discord-status');
    const dText = document.getElementById('webhook-discord-status-text');
    if (dBadge && dText) {
      if (dUrl) {
        dBadge.className = 'webhook-status-badge configured';
        dText.textContent = 'Configurado (Webhook activo)';
      } else {
        dBadge.className = 'webhook-status-badge unconfigured';
        dText.textContent = 'Sin configurar';
      }
    }

    // Telegram Status
    const tgTok = (this.config.telegram?.bot_token || '').trim();
    const tgChat = (this.config.telegram?.chat_id || '').trim();
    const tgBadge = document.getElementById('webhook-telegram-status');
    const tgText = document.getElementById('webhook-telegram-status-text');
    if (tgBadge && tgText) {
      if (tgTok && tgChat) {
        tgBadge.className = 'webhook-status-badge configured';
        tgText.textContent = `Configurado (Chat: ${tgChat})`;
      } else {
        tgBadge.className = 'webhook-status-badge unconfigured';
        tgText.textContent = 'Sin configurar';
      }
    }

    // Email Status
    const emHost = (this.config.email?.smtp_host || '').trim();
    const emTo = (this.config.email?.to_emails || '').trim();
    const emBadge = document.getElementById('webhook-email-status');
    const emText = document.getElementById('webhook-email-status-text');
    if (emBadge && emText) {
      if (emHost && emTo) {
        emBadge.className = 'webhook-status-badge configured';
        emText.textContent = `Configurado (${emHost})`;
      } else {
        emBadge.className = 'webhook-status-badge unconfigured';
        emText.textContent = 'Sin configurar';
      }
    }
  },

  openModal(channel) {
    this.currentModalChannel = channel;
    const modal = document.getElementById('webhook-config-modal');
    const titleEl = document.getElementById('webhook-modal-title');
    const secDiscord = document.getElementById('modal-section-discord');
    const secTg = document.getElementById('modal-section-telegram');
    const secEmail = document.getElementById('modal-section-email');
    const testBtn = document.getElementById('webhook-modal-test-btn');

    if (secDiscord) secDiscord.style.display = channel === 'discord' ? 'block' : 'none';
    if (secTg) secTg.style.display = channel === 'telegram' ? 'block' : 'none';
    if (secEmail) secEmail.style.display = channel === 'email' ? 'block' : 'none';

    if (titleEl) {
      const cogSvg = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:8px;"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>';
      if (channel === 'discord') titleEl.innerHTML = `${cogSvg} Configurar Webhook de Discord`;
      else if (channel === 'telegram') titleEl.innerHTML = `${cogSvg} Configurar Bot de Telegram`;
      else if (channel === 'email') titleEl.innerHTML = `${cogSvg} Configurar Correo Electrónico (SMTP)`;
    }

    if (testBtn) {
      testBtn.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> Probar ${channel.toUpperCase()}`;
    }

    if (modal) modal.classList.add('open');
  },

  closeModal() {
    const modal = document.getElementById('webhook-config-modal');
    if (modal) modal.classList.remove('open');
    this.currentModalChannel = null;
  },

  async toggleChannel(channel, isEnabled) {
    if (!this.config) this.config = {};
    if (!this.config[channel]) this.config[channel] = {};
    this.config[channel].enabled = isEnabled;

    try {
      const res = await fetch('/api/webhooks/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [channel]: { enabled: isEnabled } })
      });
      if (!res.ok) throw new Error("Error actualizando estado del canal");
      App.showToast(`Canal ${channel.toUpperCase()} ${isEnabled ? 'activado' : 'desactivado'}.`, 'info');
    } catch (err) {
      App.showToast(err.message, 'danger');
    }
  },

  async saveConfig() {
    const btnSave = document.getElementById('btn-save-webhooks');
    if (btnSave) btnSave.disabled = true;

    const payload = {
      discord: {
        enabled: document.getElementById('webhook-discord-enable')?.checked || false,
        webhook_url: (document.getElementById('webhook-discord-url')?.value || '').trim()
      },
      telegram: {
        enabled: document.getElementById('webhook-telegram-enable')?.checked || false,
        bot_token: (document.getElementById('webhook-telegram-token')?.value || '').trim(),
        chat_id: (document.getElementById('webhook-telegram-chatid')?.value || '').trim()
      },
      email: {
        enabled: document.getElementById('webhook-email-enable')?.checked || false,
        smtp_host: (document.getElementById('webhook-email-host')?.value || '').trim(),
        smtp_port: parseInt(document.getElementById('webhook-email-port')?.value || '587', 10),
        smtp_user: (document.getElementById('webhook-email-user')?.value || '').trim(),
        smtp_password: document.getElementById('webhook-email-pass')?.value || '',
        smtp_use_tls: document.getElementById('webhook-email-tls')?.checked || false,
        from_email: (document.getElementById('webhook-email-from')?.value || '').trim(),
        to_emails: (document.getElementById('webhook-email-to')?.value || '').trim()
      },
      events: {
        server_start: document.getElementById('webhook-event-start')?.checked || false,
        server_stop: document.getElementById('webhook-event-stop')?.checked || false,
        server_crash: document.getElementById('webhook-event-crash')?.checked || false,
        backup_created: document.getElementById('webhook-event-backup')?.checked || false,
        task_executed: document.getElementById('webhook-event-task')?.checked || false,
        player_join: document.getElementById('webhook-event-player')?.checked || false,
        player_leave: document.getElementById('webhook-event-player')?.checked || false
      }
    };

    try {
      const res = await fetch('/api/webhooks/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Error al guardar configuración de webhooks");

      this.config = data.config || payload;
      this.updateStatusBadges();
      App.showToast("Configuración de Webhooks guardada correctamente.", "success");
      return true;
    } catch (err) {
      console.error("[Webhooks]", err);
      App.showToast(err.message, "danger");
      return false;
    } finally {
      if (btnSave) btnSave.disabled = false;
    }
  },

  async saveFromModal() {
    const success = await this.saveConfig();
    if (success) {
      this.closeModal();
    }
  },

  async testCurrentModalChannel() {
    if (this.currentModalChannel) {
      await this.testChannel(this.currentModalChannel);
    }
  },

  async testChannel(channel) {
    const btn = document.getElementById(`btn-test-${channel}`);
    const modalBtn = document.getElementById('webhook-modal-test-btn');
    const originalText = btn ? btn.innerHTML : '';
    const origModalText = modalBtn ? modalBtn.innerHTML : '';

    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<span class="spin-icon">↻</span> Probando...`;
    }
    if (modalBtn) {
      modalBtn.disabled = true;
      modalBtn.innerHTML = `<span class="spin-icon">↻</span> Probando...`;
    }

    try {
      // Auto-save current form data before testing
      await this.saveConfig();

      App.showToast(`Enviando notificación de prueba a ${channel.toUpperCase()}...`, 'info');
      const res = await fetch(`/api/webhooks/test/${encodeURIComponent(channel)}`, {
        method: 'POST'
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `Error al probar ${channel}`);

      App.showToast(data.message || 'Notificación de prueba enviada con éxito', 'success');
    } catch (err) {
      console.error(`[Webhooks Test ${channel}]`, err);
      App.showToast(err.message, 'danger');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = originalText;
      }
      if (modalBtn) {
        modalBtn.disabled = false;
        modalBtn.innerHTML = origModalText;
      }
    }
  }
};
