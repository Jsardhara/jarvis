"use client";

import { useState } from "react";
import useSWR from "swr";
import { createTask, fetcher, patchTask, type Task } from "@/lib/api";

export default function TasksPage() {
  const { data, mutate } = useSWR<{ tasks: Task[] }>("/api/tasks", fetcher);
  const [title, setTitle] = useState("");

  const onAdd = async () => {
    const t = title.trim();
    if (!t) return;
    await createTask(t);
    setTitle("");
    mutate();
  };

  const onToggle = async (task: Task) => {
    await patchTask(task.id, { status: task.status === "open" ? "done" : "open" });
    mutate();
  };

  const tasks = data?.tasks ?? [];
  const open = tasks.filter((t) => t.status === "open");
  const done = tasks.filter((t) => t.status === "done");

  return (
    <>
      <h1>Tasks</h1>
      <div className="card" style={{ marginBottom: "1rem" }}>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <input
            placeholder="New task…"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onAdd()}
          />
          <button onClick={onAdd}>Add</button>
        </div>
      </div>

      <div className="grid">
        <section className="card">
          <h2>Open ({open.length})</h2>
          {open.length === 0 ? (
            <p className="muted">Nothing open.</p>
          ) : (
            open.map((t) => (
              <div key={t.id} className="row">
                <input type="checkbox" style={{ width: "auto" }} onChange={() => onToggle(t)} />
                <span>{t.title}</span>
                {t.tags.map((tag) => (
                  <span key={tag} className="muted mono">
                    #{tag}
                  </span>
                ))}
              </div>
            ))
          )}
        </section>
        <section className="card">
          <h2>Done ({done.length})</h2>
          {done.slice(-10).map((t) => (
            <div key={t.id} className="row" style={{ opacity: 0.6 }}>
              <input type="checkbox" checked readOnly style={{ width: "auto" }} onClick={() => onToggle(t)} />
              <span style={{ textDecoration: "line-through" }}>{t.title}</span>
            </div>
          ))}
        </section>
      </div>
    </>
  );
}
