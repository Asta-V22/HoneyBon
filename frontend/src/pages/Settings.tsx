import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { ModelPicker } from "../components/ModelPicker";
import { Button, Card, ErrorText, Field, inputClass, PageHeader, SectionTitle } from "../components/ui";
import { api, PROVIDER_LABELS, type Me } from "../lib/api";
import { useMe, useUpdateMe } from "../lib/hooks";


export function SettingsPage() {
  const { data: me } = useMe();
  if (!me) return null;
  return (
    <div className="flex max-w-2xl flex-col gap-8">
      <PageHeader title="Settings" eyebrow={`Signed in as ${me.github_login}`} />
      <ProviderKeys me={me} />
      <DefaultModel me={me} />
      <section className="flex flex-col gap-3">
        <SectionTitle aside="Phase 2">Extension tokens</SectionTitle>
        <Card className="p-4 text-sm text-text-muted">
          The LeetCode extension and its access tokens arrive with automatic capture.
        </Card>
      </section>
      <DataSection me={me} />
    </div>
  );
}

function useSetMe() {
  const qc = useQueryClient();
  return (me: Me) => qc.setQueryData(["me"], me);
}

function ProviderKeys({ me }: { me: Me }) {
  return (
    <section className="flex flex-col gap-3">
      <SectionTitle aside="Encrypted at rest; only the last four characters are ever shown">API keys</SectionTitle>
      <Card className="divide-y divide-divider">
        {me.available_providers.map((p) => (
          <ProviderKeyRow key={p} provider={p} saved={me.providers.find((k) => k.provider === p)} />
        ))}
      </Card>
    </section>
  );
}

function ProviderKeyRow({ provider, saved }: { provider: string; saved?: Me["providers"][number] }) {
  const setMe = useSetMe();
  const [key, setKey] = useState("");
  const save = useMutation({
    mutationFn: () => api.saveKey(provider, key.trim()),
    onSuccess: (me) => {
      setMe(me);
      setKey("");
    },
  });
  const remove = useMutation({ mutationFn: () => api.deleteKey(provider), onSuccess: setMe });
  const id = `key-${provider}`;

  return (
    <form
      className="flex flex-col gap-2 p-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (key.trim()) save.mutate();
      }}
    >
      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor={id} className="w-24 font-medium">
          {PROVIDER_LABELS[provider] ?? provider}
        </label>
        <input
          id={id}
          type="password"
          autoComplete="off"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder={saved ? `•••• ${saved.last_four}` : "Paste API key"}
          className={`${inputClass} flex-[1_1_200px] font-mono text-xs`}
        />
        <Button type="submit" disabled={!key.trim() || save.isPending}>
          {saved ? "Replace" : "Save"}
        </Button>
        {saved && (
          <Button onClick={() => remove.mutate()} disabled={remove.isPending}>
            Remove
          </Button>
        )}
      </div>
      <ErrorText error={save.error ?? remove.error} />
    </form>
  );
}

function DefaultModel({ me }: { me: Me }) {
  const update = useUpdateMe();
  const [provider, setProvider] = useState(me.default_provider ?? "");
  const firstModel = (p: string) => me.provider_models[p]?.[0] ?? "";
  const [model, setModel] = useState(me.default_model ?? firstModel(provider));
  useEffect(() => {
    setProvider(me.default_provider ?? "");
    setModel(me.default_model ?? firstModel(me.default_provider ?? ""));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me.default_provider, me.default_model]);

  const saved = me.providers.map((p) => p.provider);
  return (
    <section className="flex flex-col gap-3">
      <SectionTitle aside="Overridable per review">Default model</SectionTitle>
      <Card className="p-4">
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            update.mutate({ default_provider: provider || null, default_model: model.trim() || null });
          }}
        >
          <div className="w-40">
            <Field label="Provider" htmlFor="default-provider">
              <select
                id="default-provider"
                value={provider}
                onChange={(e) => {
                  setProvider(e.target.value);
                  setModel(firstModel(e.target.value));
                }}
                className={inputClass}
                disabled={saved.length === 0}
              >
                {saved.length === 0 && <option value="">Add a key first</option>}
                {saved.map((p) => (
                  <option key={p} value={p}>
                    {PROVIDER_LABELS[p] ?? p}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <div className="flex-[1_1_220px]">
            <Field label="Model" htmlFor="default-model">
              <ModelPicker
                id="default-model"
                models={me.provider_models[provider] ?? []}
                value={model}
                onChange={setModel}
              />
            </Field>
          </div>
          <Button type="submit" disabled={update.isPending || saved.length === 0 || !model.trim()}>
            Save
          </Button>
        </form>
        <ErrorText error={update.error} />
      </Card>
    </section>
  );
}

function DataSection({ me }: { me: Me }) {
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState("");
  const del = useMutation({
    mutationFn: api.deleteAccount,
    onSuccess: () => qc.clear(),
  });
  return (
    <section className="flex flex-col gap-3">
      <SectionTitle>Your data</SectionTitle>
      <Card className="flex flex-col gap-4 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-text-secondary">Download every submission and review as JSON.</p>
          <a
            href="/api/me/export"
            download="honeybon-export.json"
            className="inline-flex min-h-8 items-center rounded-lg border border-border-strong bg-chip px-3 text-[13px] text-text no-underline hover:bg-selected"
          >
            Export
          </a>
        </div>
        <div className="flex flex-col gap-2 border-t border-divider pt-4">
          <label htmlFor="confirm-delete" className="text-sm text-text-secondary">
            Delete your account and everything in it. Type <code className="font-mono">{me.github_login}</code> to
            confirm.
          </label>
          <div className="flex flex-wrap gap-2">
            <input
              id="confirm-delete"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className={`${inputClass} flex-[1_1_200px]`}
            />
            <Button variant="danger" disabled={confirm !== me.github_login || del.isPending} onClick={() => del.mutate()}>
              Delete account
            </Button>
          </div>
          <ErrorText error={del.error} />
        </div>
      </Card>
    </section>
  );
}
