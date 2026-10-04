import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, ApiError, type Me } from "./api";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    retry: (count, error) => !(error instanceof ApiError && error.status === 401) && count < 2,
  });
}

export function useUpdateMe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.updateMe,
    onMutate: async (patch) => {
      await qc.cancelQueries({ queryKey: ["me"] });
      const previous = qc.getQueryData<Me>(["me"]);
      if (previous) qc.setQueryData<Me>(["me"], { ...previous, ...patch });
      return { previous };
    },
    onError: (_e, _v, ctx) => ctx?.previous && qc.setQueryData(["me"], ctx.previous),
    onSuccess: (me) => qc.setQueryData(["me"], me),
  });
}

/** j/k to move through a list, Enter to open. Ignored while typing in a field. */
export function useListNavigation(paths: string[]) {
  const [index, setIndex] = useState(-1);
  const navigate = useNavigate();

  useEffect(() => setIndex((i) => Math.min(i, paths.length - 1)), [paths.length]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement;
      if (el.closest("input, textarea, select, [contenteditable=true]") || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "j") setIndex((i) => Math.min(i + 1, paths.length - 1));
      else if (e.key === "k") setIndex((i) => Math.max(i - 1, 0));
      else if (e.key === "Enter" && index >= 0 && paths[index] && !el.closest("a, button")) navigate(paths[index]);
      else return;
      e.preventDefault();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [paths, index, navigate]);

  return index;
}
