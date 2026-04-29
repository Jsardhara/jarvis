/* global React, AGENTS, TASKS, COLUMNS, AgentGlyph, Tag, Progress, Dot */
// ═══════════════════════════════════════════════════════════════
// KANBAN VIEW
// Watch Jarvis route tasks across columns
// ═══════════════════════════════════════════════════════════════

const { useState: useStateKb, useEffect: useEffectKb, useMemo: useMemoKb } = React;

function priorityColor(p) {
  return p === 'p0' ? 'var(--crit)'
    : p === 'p1' ? 'var(--amber)'
    : p === 'p2' ? 'var(--info)'
    : 'var(--fg-dim)';
}

function TaskCard({ task, animating, onOpen }) {
  const agent = task.agent ? AGENTS.find((a) => a.id === task.agent) : null;
  return (
    <div
      onClick={() => onOpen && onOpen(task)}
      style={{
        background: 'var(--bg-elevated)',
        border: '1px solid var(--line)',
        borderLeft: `2px solid ${priorityColor(task.priority)}`,
        padding: '10px 12px',
        marginBottom: 8,
        cursor: 'pointer',
        position: 'relative',
        transition: 'border-color 120ms, transform 320ms, opacity 320ms',
        transform: animating ? 'translateY(-4px)' : 'translateY(0)',
        opacity: animating ? 0.6 : 1,
      }}
      onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--line-bright)'; }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--line)'; }}
    >
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: 6,
      }}>
        <span style={{
          fontSize: 9, letterSpacing: '0.14em', color: 'var(--fg-faint)',
          fontFamily: 'var(--mono)',
        }}>{task.id}</span>
        <span style={{
          fontSize: 9, letterSpacing: '0.14em', textTransform: 'uppercase',
          color: priorityColor(task.priority), fontWeight: 600,
        }}>{task.priority}</span>
      </div>

      <div style={{
        fontSize: 12, color: 'var(--fg)', lineHeight: 1.4,
        marginBottom: 8, fontFamily: 'var(--sans)',
      }}>{task.title}</div>

      {task.preview && (
        <div style={{
          fontSize: 10, color: 'var(--fg-dim)', lineHeight: 1.45,
          marginBottom: 8, fontStyle: 'italic',
        }}>{task.preview}</div>
      )}

      {typeof task.progress === 'number' && (
        <div style={{ marginBottom: 8 }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between',
            fontSize: 9, letterSpacing: '0.1em', color: 'var(--fg-dim)',
            marginBottom: 3,
          }}>
            <span>PROGRESS</span>
            <span>{Math.round(task.progress * 100)}%</span>
          </div>
          <Progress value={task.progress} color={agent ? agent.colorHex : 'var(--amber)'} />
        </div>
      )}

      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        paddingTop: 6, borderTop: '1px solid var(--line)',
      }}>
        {agent ? (
          <>
            <AgentGlyph agent={agent} size={14} />
            <span style={{ fontSize: 10, color: agent.colorHex, letterSpacing: '0.08em' }}>
              {agent.name}
            </span>
          </>
        ) : (
          <span style={{ fontSize: 10, color: 'var(--fg-faint)', letterSpacing: '0.08em' }}>
            ◇ UNROUTED
          </span>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--fg-faint)' }}>
          {task.source} · {task.age}
        </span>
      </div>
    </div>
  );
}

function KanbanColumn({ col, tasks, onOpen }) {
  const accent = col.id === 'inbox' ? 'var(--amber)'
    : col.id === 'active' ? 'var(--info)'
    : col.id === 'blocked' ? 'var(--crit)'
    : col.id === 'done' ? 'var(--ok)'
    : 'var(--fg-dim)';
  return (
    <div style={{
      flex: '0 0 280px',
      background: 'var(--bg-panel)',
      border: '1px solid var(--line)',
      borderTop: `2px solid ${accent}`,
      display: 'flex',
      flexDirection: 'column',
      minHeight: 0,
    }}>
      <div style={{
        padding: '10px 12px',
        borderBottom: '1px solid var(--line)',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
      }}>
        <span style={{
          fontFamily: 'var(--sans)',
          fontSize: 11,
          letterSpacing: '0.14em',
          color: 'var(--fg)',
          fontWeight: 600,
        }}>{col.label}</span>
        <span style={{
          fontSize: 9, letterSpacing: '0.1em', color: 'var(--fg-faint)',
        }}>{col.sub}</span>
        <span style={{
          marginLeft: 'auto',
          fontFamily: 'var(--mono)',
          fontSize: 11,
          color: accent,
          fontVariantNumeric: 'tabular-nums',
        }}>{tasks.length.toString().padStart(2, '0')}</span>
      </div>
      <div style={{
        flex: 1, overflow: 'auto', padding: 10,
        background: 'linear-gradient(180deg, transparent 0%, transparent 100%)',
      }}>
        {tasks.length === 0 ? (
          <div style={{
            padding: 20, textAlign: 'center',
            fontSize: 10, color: 'var(--fg-faint)', letterSpacing: '0.18em',
            border: '1px dashed var(--line)',
          }}>— empty —</div>
        ) : tasks.map((t) => <TaskCard key={t.id} task={t} onOpen={onOpen} />)}
      </div>
    </div>
  );
}

function KanbanView({ onOpenTask }) {
  const [tasks, setTasks] = useStateKb(TASKS);
  const [filter, setFilter] = useStateKb('all');

  const filtered = useMemoKb(() => {
    if (filter === 'all') return tasks;
    return tasks.filter((t) => t.agent === filter);
  }, [tasks, filter]);

  // Occasional task-flow animation: move a task one column to the right
  useEffectKb(() => {
    const flow = ['inbox', 'classified', 'dispatched', 'active', 'done'];
    const id = setInterval(() => {
      setTasks((cur) => {
        // pick an active task and bump progress, or move one along the flow
        const idx = Math.floor(Math.random() * cur.length);
        const t = cur[idx];
        if (!t) return cur;
        const nextCol = flow[Math.min(flow.indexOf(t.column) + 1, flow.length - 1)];
        if (t.column === 'active' && typeof t.progress === 'number') {
          const newProg = Math.min(t.progress + 0.05 + Math.random() * 0.1, 1);
          const updated = { ...t, progress: newProg };
          if (newProg >= 1) updated.column = 'done';
          return cur.map((x, i) => i === idx ? updated : x);
        }
        return cur;
      });
    }, 2400);
    return () => clearInterval(id);
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{
        padding: '10px 20px',
        borderBottom: '1px solid var(--line)',
        display: 'flex', alignItems: 'center', gap: 12,
        background: 'var(--bg-deep)',
      }}>
        <span style={{ fontSize: 10, letterSpacing: '0.18em', color: 'var(--fg-dim)' }}>
          FILTER · AGENT
        </span>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          <FilterChip active={filter === 'all'} onClick={() => setFilter('all')}>ALL · {tasks.length}</FilterChip>
          {AGENTS.map((a) => {
            const count = tasks.filter((t) => t.agent === a.id).length;
            return (
              <FilterChip
                key={a.id}
                active={filter === a.id}
                onClick={() => setFilter(a.id)}
                accent={a.colorHex}
              >
                {a.name} · {count}
              </FilterChip>
            );
          })}
        </div>
      </div>

      <div style={{
        flex: 1,
        overflow: 'auto',
        padding: 16,
      }}>
        <div style={{
          display: 'flex',
          gap: 12,
          height: '100%',
          minHeight: 480,
        }}>
          {COLUMNS.map((c) => (
            <KanbanColumn
              key={c.id}
              col={c}
              tasks={filtered.filter((t) => t.column === c.id)}
              onOpen={onOpenTask}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function FilterChip({ active, onClick, accent, children }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: active ? 'var(--bg-elevated)' : 'transparent',
        border: `1px solid ${active ? (accent || 'var(--amber)') : 'var(--line)'}`,
        color: active ? (accent || 'var(--amber)') : 'var(--fg-mute)',
        padding: '4px 8px',
        fontSize: 10,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        borderRadius: 2,
        fontFamily: 'var(--mono)',
      }}
    >{children}</button>
  );
}

window.KanbanView = KanbanView;
