const board = document.querySelector('[data-pipeline-board]');

if (board) {
  const columns = Array.from(board.querySelectorAll('[data-stage-column]'));
  let draggedCard = null;

  const formatCurrency = (value, currency) => {
    const symbol = currency || '₹';
    const amount = Number.isFinite(value) ? value : 0;
    return `${symbol}${amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  const applyDraggable = (card) => {
    if (card.dataset.draggableApplied) {
      return;
    }

    card.dataset.draggableApplied = 'true';
    card.setAttribute('draggable', 'true');

    card.addEventListener('dragstart', (event) => {
      draggedCard = card;
      card.classList.add('opacity-70');
      event.dataTransfer.effectAllowed = 'move';
    });

    card.addEventListener('dragend', () => {
      card.classList.remove('opacity-70');
      draggedCard = null;
      columns.forEach(clearHighlight);
    });
  };

  board.querySelectorAll('[data-opportunity-card]').forEach(applyDraggable);

  columns.forEach((column) => {
    column.addEventListener('dragover', (event) => {
      if (!draggedCard) {
        return;
      }
      event.preventDefault();
      event.dataTransfer.dropEffect = 'move';
      column.classList.add('ring-2', 'ring-emerald-400/40');
    });

    column.addEventListener('dragleave', (event) => {
      if (!draggedCard) {
        return;
      }
      if (!column.contains(event.relatedTarget)) {
        clearHighlight(column);
      }
    });

    column.addEventListener('drop', (event) => {
      if (!draggedCard) {
        return;
      }
      event.preventDefault();
      clearHighlight(column);

      const targetStage = column.dataset.stage;
      const cardsContainer = column.querySelector('[data-stage-cards]');
      if (!targetStage || !cardsContainer) {
        return;
      }

      const card = draggedCard;
      const currentStage = card.dataset.stage;

      if (currentStage === targetStage) {
        cardsContainer.appendChild(card);
        ensureEmptyState(currentStage);
        ensureEmptyState(targetStage);
        return;
      }

      updateOpportunityStage(card, currentStage, targetStage, cardsContainer);
    });
  });

  function clearHighlight(column) {
    column.classList.remove('ring-2', 'ring-emerald-400/40');
  }

  function updateOpportunityStage(card, fromStage, toStage, targetContainer) {
    const url = card.dataset.stageUrl;
    if (!url) {
      return;
    }

    const amountValue = parseFloat(card.dataset.amount || '0');
    const cardCurrency = card.dataset.currency || '₹';

    card.classList.add('pointer-events-none');

    const params = new URLSearchParams();
    params.set('stage', toStage);

    fetch(url, {
      method: 'POST',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: params,
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error('Unable to update opportunity stage.');
        }
        return response.json();
      })
      .then((data) => {
        if (!data.success) {
          throw new Error(data.message || 'Unable to update opportunity stage.');
        }

        targetContainer.appendChild(card);
        card.dataset.stage = toStage;

        if (typeof data.has_project === 'boolean') {
          card.dataset.hasProject = data.has_project ? 'true' : 'false';
        }
        if (data.convert_url) {
          card.dataset.convertUrl = data.convert_url;
        }

        adjustCount(fromStage, -1);
        adjustCount(toStage, 1);
        adjustTotals(fromStage, -amountValue, cardCurrency);
        adjustTotals(toStage, amountValue, cardCurrency);
        ensureEmptyState(fromStage);
        ensureEmptyState(toStage);

        maybePromptProjectConversion(card, toStage);
      })
      .catch((error) => {
        console.error(error);
        window.alert(error.message || 'Unable to update opportunity stage.');
      })
      .finally(() => {
        card.classList.remove('pointer-events-none');
      });
  }

  function adjustCount(stage, delta) {
    if (!stage) {
      return;
    }

    const countElements = board.querySelectorAll('[data-stage-count]');
    countElements.forEach((element) => {
      if (element.dataset.stage !== stage) {
        return;
      }
      const current = parseInt(element.dataset.count || '0', 10);
      const next = Math.max(0, current + delta);
      element.dataset.count = String(next);
      element.textContent = next === 1 ? '1 deal' : `${next} deals`;
    });

    const summaryElements = document.querySelectorAll('[data-stage-summary]');
    summaryElements.forEach((element) => {
      if (element.dataset.stage !== stage) {
        return;
      }
      const current = parseInt(element.dataset.count || '0', 10);
      const next = Math.max(0, current + delta);
      element.dataset.count = String(next);
      element.textContent = next === 1 ? '1 deal' : `${next} deals`;
    });
  }

  function adjustTotals(stage, delta, currencyHint) {
    if (!stage || !Number.isFinite(delta) || delta === 0) {
      return;
    }

    const normalizeTotal = (current, change) => {
      const next = (Number.isFinite(current) ? current : 0) + change;
      return Math.max(0, next);
    };

    const updateElements = (elements) => {
      elements.forEach((element) => {
        if (element.dataset.stage !== stage) {
          return;
        }
        const currentTotal = parseFloat(element.dataset.total || '0');
        const nextTotal = normalizeTotal(currentTotal, delta);
        let currency = element.dataset.currency || currencyHint || '₹';
        if (((!element.dataset.currency || element.dataset.currency === '') || currentTotal === 0) && currencyHint) {
          currency = currencyHint;
        }
        element.dataset.currency = currency;
        element.dataset.total = String(nextTotal);
        element.textContent = `Value ${formatCurrency(nextTotal, currency)}`;
      });
    };

    updateElements(board.querySelectorAll('[data-stage-total]'));
    updateElements(document.querySelectorAll('[data-stage-summary-total]'));
  }

  function ensureEmptyState(stage) {
    if (!stage) {
      return;
    }

    const column = columns.find((col) => col.dataset.stage === stage);
    if (!column) {
      return;
    }

    const container = column.querySelector('[data-stage-cards]');
    const emptyMessage = column.querySelector('[data-empty-message]');
    if (!container || !emptyMessage) {
      return;
    }

    const hasCard = container.querySelector('[data-opportunity-card]');
    emptyMessage.classList.toggle('hidden', Boolean(hasCard));
  }

  function maybePromptProjectConversion(card, toStage) {
    const normalizedStage = (toStage || '').trim().toLowerCase();
    if (!normalizedStage.includes('closed won')) {
      return;
    }

    if (card.dataset.hasProject === 'true') {
      return;
    }

    const convertUrl = card.dataset.convertUrl;
    if (!convertUrl) {
      return;
    }

    const shouldConvert = window.confirm(
      'This opportunity is Closed Won. Do you want to convert it into a project now?',
    );
    if (!shouldConvert) {
      return;
    }

    const form = document.createElement('form');
    form.method = 'POST';
    form.action = convertUrl;
    form.style.display = 'none';
    document.body.appendChild(form);
    form.submit();
  }
}
