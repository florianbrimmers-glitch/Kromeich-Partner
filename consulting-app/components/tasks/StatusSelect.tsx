"use client";

import { useTransition } from "react";
import { STATUS_LABELS } from "@/lib/utils";

const STATUSES = ["TODO", "IN_PROGRESS", "REVIEW", "DONE"] as const;

export function StatusSelect({
  taskId,
  current,
  action,
}: {
  taskId: string;
  current: string;
  action: (formData: FormData) => Promise<void>;
}) {
  const [pending, start] = useTransition();

  return (
    <select
      defaultValue={current}
      disabled={pending}
      className="input text-xs py-1 max-w-[140px]"
      onChange={(e) => {
        const fd = new FormData();
        fd.set("id", taskId);
        fd.set("status", e.currentTarget.value);
        start(() => action(fd));
      }}
    >
      {STATUSES.map((s) => (
        <option key={s} value={s}>
          {STATUS_LABELS[s]}
        </option>
      ))}
    </select>
  );
}
