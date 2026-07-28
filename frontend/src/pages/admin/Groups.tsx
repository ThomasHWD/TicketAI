import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch, setChefGroupe } from "../../lib/api";
import type { Groupe, MembreSummary, UserSummary } from "../../types";
import {
  Plus,
  Trash2,
  UserPlus,
  UserMinus,
  X,
  Users,
  Search,
  ShieldCheck,
  FolderOpen,
  AlertTriangle,
  Loader2,
  Crown,
  ChevronRight,
} from "lucide-react";

// ── API ──────────────────────────────────────────────────────────────

async function fetchGroupes(): Promise<Groupe[]> {
  const res = await apiFetch("/api/v1/admin/groupes");
  return res.json();
}
async function fetchGestionnaires(): Promise<UserSummary[]> {
  const res = await apiFetch("/api/v1/admin/gestionnaires");
  return res.json();
}
async function fetchDomaines(): Promise<string[]> {
  const res = await apiFetch("/api/v1/admin/domaines");
  return res.json();
}
async function createGroupe(body: { nom: string; domaine: string }): Promise<Groupe> {
  const res = await apiFetch("/api/v1/admin/groupes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data?.detail ?? "Erreur lors de la création.");
  }
  return res.json();
}
async function deleteGroupe(id: string): Promise<void> {
  await apiFetch(`/api/v1/admin/groupes/${id}`, { method: "DELETE" });
}
async function addMembre(groupeId: string, userId: string): Promise<Groupe> {
  const res = await apiFetch(`/api/v1/admin/groupes/${groupeId}/membres/${userId}`, { method: "POST" });
  return res.json();
}
async function removeMembre(groupeId: string, userId: string): Promise<void> {
  await apiFetch(`/api/v1/admin/groupes/${groupeId}/membres/${userId}`, { method: "DELETE" });
}

// ── Modals de confirmation ───────────────────────────────────────────

function ConfirmDeleteGroupe({ groupe, onConfirm, onCancel, isPending }: {
  groupe: Groupe;
  onConfirm: () => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onCancel}>
      <div className="absolute inset-0 bg-black/30 dark:bg-black/60 backdrop-blur-sm" />
      <div className="relative glass-card rounded-2xl w-full max-w-sm p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-red-100 dark:bg-red-400/15 shrink-0">
            <AlertTriangle size={18} className="text-red-600 dark:text-red-400" />
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">Supprimer ce groupe ?</p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate max-w-[220px]">{groupe.nom}</p>
          </div>
        </div>
        <p className="text-xs text-gray-600 dark:text-gray-400">
          Le groupe sera supprimé ainsi que toutes ses associations membres. Cette action est irréversible.
        </p>
        <div className="flex gap-2 pt-1">
          <button
            onClick={onCancel}
            disabled={isPending}
            className="flex-1 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 disabled:opacity-50 transition-colors"
          >
            Annuler
          </button>
          <button
            onClick={onConfirm}
            disabled={isPending}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-red-600 hover:bg-red-700 dark:bg-red-600 dark:hover:bg-red-500 text-white disabled:opacity-50 transition-colors"
          >
            {isPending ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
            Supprimer
          </button>
        </div>
      </div>
    </div>
  );
}

function ConfirmRetireMembre({ membre, onConfirm, onCancel, isPending }: {
  membre: UserSummary;
  onConfirm: () => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  const name = membre.prenom && membre.nom ? `${membre.prenom} ${membre.nom}` : membre.email;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onCancel}>
      <div className="absolute inset-0 bg-black/30 dark:bg-black/60 backdrop-blur-sm" />
      <div className="relative glass-card rounded-2xl w-full max-w-sm p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-red-100 dark:bg-red-400/15 shrink-0">
            <UserMinus size={18} className="text-red-600 dark:text-red-400" />
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">Retirer ce membre ?</p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate max-w-[220px]">{name}</p>
          </div>
        </div>
        <p className="text-xs text-gray-600 dark:text-gray-400">
          Le gestionnaire perdra l'accès aux tickets et documents de ce domaine jusqu'à être réaffecté.
        </p>
        <div className="flex gap-2 pt-1">
          <button
            onClick={onCancel}
            disabled={isPending}
            className="flex-1 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 disabled:opacity-50 transition-colors"
          >
            Annuler
          </button>
          <button
            onClick={onConfirm}
            disabled={isPending}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-red-600 hover:bg-red-700 dark:bg-red-600 dark:hover:bg-red-500 text-white disabled:opacity-50 transition-colors"
          >
            {isPending ? <Loader2 size={14} className="animate-spin" /> : <UserMinus size={14} />}
            Retirer
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Combobox domaine ─────────────────────────────────────────────────

function DomaineCombobox({ value, onChange, existing }: {
  value: string;
  onChange: (v: string) => void;
  existing: string[];
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const q = value.trim().toUpperCase();
  const matches = existing.filter((d) => d.includes(q));
  const canCreate = q.length > 0 && matches.length === 0;

  useEffect(() => {
    function onOut(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onOut);
    return () => document.removeEventListener("mousedown", onOut);
  }, []);

  return (
    <div ref={ref} className="relative">
      <input
        required
        type="text"
        value={value}
        placeholder="ex : RH"
        onFocus={() => setOpen(true)}
        onChange={(e) => { onChange(e.target.value.toUpperCase()); setOpen(true); }}
        className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-sm text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
      />
      {open && (matches.length > 0 || canCreate) && (
        <ul className="absolute z-30 mt-1 w-full rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-gray-900 shadow-xl overflow-hidden">
          {matches.map((d) => (
            <li key={d} className="flex items-center justify-between px-3 py-2.5 text-sm text-gray-400 dark:text-gray-500 select-none cursor-not-allowed">
              <span className="font-mono">{d}</span>
              <span className="text-xs bg-gray-100 dark:bg-white/5 px-1.5 py-0.5 rounded">déjà utilisé</span>
            </li>
          ))}
          {canCreate && (
            <li>
              <button
                type="button"
                onMouseDown={() => { onChange(q); setOpen(false); }}
                className="w-full text-left px-3 py-2.5 text-sm font-medium text-emerald-700 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-400/10 flex items-center gap-2"
              >
                <Plus size={13} />
                Créer «&nbsp;<span className="font-mono">{q}</span>&nbsp;»
              </button>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────

function displayName(u: UserSummary) {
  return u.prenom && u.nom ? `${u.prenom} ${u.nom}` : u.email;
}

function initials(u: UserSummary) {
  if (u.prenom && u.nom) return `${u.prenom[0]}${u.nom[0]}`.toUpperCase();
  return u.email.slice(0, 2).toUpperCase();
}

// ── Composant principal ──────────────────────────────────────────────

export default function GroupsPage() {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["admin", "groupes"] });
    queryClient.invalidateQueries({ queryKey: ["admin", "gestionnaires"] });
    queryClient.invalidateQueries({ queryKey: ["admin", "domaines"] });
  };

  const { data: groupes = [], isLoading } = useQuery({ queryKey: ["admin", "groupes"], queryFn: fetchGroupes });
  const { data: gestionnaires = [] } = useQuery({ queryKey: ["admin", "gestionnaires"], queryFn: fetchGestionnaires });
  const { data: domaines = [] } = useQuery({ queryKey: ["admin", "domaines"], queryFn: fetchDomaines });

  const [createError, setCreateError] = useState<string | null>(null);
  const createMut = useMutation({
    mutationFn: createGroupe,
    onSuccess: invalidate,
    onError: (err: unknown) => setCreateError(err instanceof Error ? err.message : "Erreur lors de la création."),
  });
  const deleteMut = useMutation({ mutationFn: deleteGroupe, onSuccess: invalidate });
  const addMut = useMutation({ mutationFn: ({ gId, uId }: { gId: string; uId: string }) => addMembre(gId, uId), onSuccess: invalidate });
  const removeMut = useMutation({ mutationFn: ({ gId, uId }: { gId: string; uId: string }) => removeMembre(gId, uId), onSuccess: invalidate });
  const chefMut = useMutation({ mutationFn: ({ gId, uId, isChef }: { gId: string; uId: string; isChef: boolean }) => setChefGroupe(gId, uId, isChef), onSuccess: invalidate });

  const [selectedGroupeId, setSelectedGroupeId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ nom: "", domaine: "" });
  const [search, setSearch] = useState("");
  const [confirmDeleteGroupe, setConfirmDeleteGroupe] = useState<Groupe | null>(null);
  const [confirmRetireMembre, setConfirmRetireMembre] = useState<UserSummary | null>(null);

  const selectedGroupe = groupes.find((g) => g.id === selectedGroupeId) ?? null;
  const memberIds = new Set(selectedGroupe?.membres.map((m) => m.id) ?? []);

  const filteredCandidates = gestionnaires.filter((u) => {
    if (memberIds.has(u.id)) return false;
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return displayName(u).toLowerCase().includes(q) || u.email.toLowerCase().includes(q) || (u.departement ?? "").toLowerCase().includes(q);
  });

  function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!form.nom.trim() || !form.domaine.trim()) return;
    setCreateError(null);
    createMut.mutate(form, {
      onSuccess: (g) => {
        setForm({ nom: "", domaine: "" });
        setShowCreate(false);
        setSelectedGroupeId(g.id);
      },
    });
  }

  return (
    <div className="p-6 space-y-5">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-800 dark:text-gray-100">
            Groupes &amp; gestionnaires
          </h1>
        </div>
        <button
          onClick={() => { setShowCreate((v) => !v); setCreateError(null); }}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 active:bg-emerald-800 text-white text-sm font-medium transition-colors shadow-sm shrink-0"
        >
          <Plus size={15} />
          Nouveau groupe
        </button>
      </div>

      {/* Formulaire création */}
      {showCreate && (
        <div className="glass-card rounded-2xl overflow-hidden">
          <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-200 dark:border-white/10">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-emerald-100 dark:bg-emerald-400/15 shrink-0">
              <FolderOpen size={15} className="text-emerald-700 dark:text-emerald-400" />
            </div>
            <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Nouveau groupe</h2>
          </div>
          <form onSubmit={handleCreate} className="px-6 py-5 flex flex-wrap gap-4 items-end">
            <div className="flex flex-col gap-1.5 flex-1 min-w-48">
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Nom du groupe</label>
              <input
                required
                value={form.nom}
                onChange={(e) => setForm((f) => ({ ...f, nom: e.target.value }))}
                placeholder="ex : Validateurs RH"
                className="px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-sm text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
              />
            </div>
            <div className="flex flex-col gap-1.5 w-44">
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Domaine</label>
              <DomaineCombobox value={form.domaine} onChange={(v) => setForm((f) => ({ ...f, domaine: v }))} existing={domaines} />
            </div>
            <div className="flex flex-col gap-2">
              {createError && <p className="text-xs text-red-600 dark:text-red-400">{createError}</p>}
              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={createMut.isPending}
                  className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-sm font-medium transition-colors"
                >
                  {createMut.isPending ? <Loader2 size={14} className="animate-spin" /> : "Créer"}
                </button>
                <button
                  type="button"
                  onClick={() => { setShowCreate(false); setCreateError(null); setForm({ nom: "", domaine: "" }); }}
                  className="px-4 py-2 rounded-lg border border-gray-200 dark:border-white/10 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                >
                  Annuler
                </button>
              </div>
            </div>
          </form>
        </div>
      )}

      {/* Contenu principal : liste groupes + panel membres */}
      <div className="flex gap-4 items-start">

        {/* Colonne gauche : liste des groupes */}
        <div className="glass-card rounded-2xl overflow-hidden w-68 shrink-0" style={{ width: "17rem" }}>
          <div className="px-4 py-3.5 border-b border-gray-200 dark:border-white/10">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Groupes</span>
              {groupes.length > 0 && (
                <span className="text-xs font-medium text-gray-400 dark:text-gray-500 tabular-nums">
                  {groupes.length}
                </span>
              )}
            </div>
          </div>

          {isLoading ? (
            <div className="px-5 py-10 text-center">
              <Loader2 size={18} className="animate-spin mx-auto text-gray-300 dark:text-gray-600" />
            </div>
          ) : groupes.length === 0 ? (
            <div className="px-5 py-10 text-center">
              <Users size={24} className="mx-auto text-gray-300 dark:text-gray-600 mb-3" />
              <p className="text-sm text-gray-500 dark:text-gray-400">Aucun groupe créé.</p>
              <p className="text-xs text-gray-400 dark:text-gray-600 mt-1">Cliquez sur « Nouveau groupe ».</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-white/5">
              {groupes.map((g) => {
                const isSelected = selectedGroupeId === g.id;
                return (
                  <button
                    key={g.id}
                    onClick={() => { setSelectedGroupeId(g.id); setSearch(""); }}
                    className={`w-full text-left px-4 py-3 transition-colors flex items-center gap-3 group ${
                      isSelected
                        ? "bg-emerald-50 dark:bg-emerald-400/10"
                        : "hover:bg-gray-50 dark:hover:bg-white/5"
                    }`}
                  >
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-xs font-bold font-mono transition-colors ${
                      isSelected
                        ? "bg-emerald-600 text-white"
                        : "bg-gray-100 dark:bg-white/10 text-gray-500 dark:text-gray-400"
                    }`}>
                      {g.domaine.slice(0, 2)}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className={`text-sm font-medium truncate transition-colors ${
                        isSelected ? "text-emerald-800 dark:text-emerald-300" : "text-gray-800 dark:text-gray-100"
                      }`}>
                        {g.nom}
                      </p>
                      <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                        {g.nb_membres} membre{g.nb_membres !== 1 ? "s" : ""}
                      </p>
                    </div>
                    <ChevronRight size={14} className={`shrink-0 transition-all ${
                      isSelected ? "text-emerald-500 opacity-100" : "text-gray-300 dark:text-gray-600 opacity-0 group-hover:opacity-100"
                    }`} />
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Colonne droite : panel membres */}
        {selectedGroupe ? (
          <div className="glass-card rounded-2xl overflow-hidden flex-1 flex flex-col" style={{ minHeight: "480px" }}>
            {/* En-tête panel */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-white/10">
              <div className="flex items-center gap-3 min-w-0">
                <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-emerald-600 shrink-0">
                  <span className="text-xs font-bold text-white font-mono">{selectedGroupe.domaine.slice(0, 2)}</span>
                </div>
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">{selectedGroupe.nom}</h3>
                  <p className="text-xs text-gray-400 dark:text-gray-500 font-mono">{selectedGroupe.domaine}</p>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => setConfirmDeleteGroupe(selectedGroupe)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-200 dark:border-red-400/20 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-400/10 text-xs font-medium transition-colors"
                >
                  <Trash2 size={12} />
                  Supprimer
                </button>
                <button
                  onClick={() => setSelectedGroupeId(null)}
                  className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors"
                >
                  <X size={15} />
                </button>
              </div>
            </div>

            <div className="flex flex-1 min-h-0 divide-x divide-gray-100 dark:divide-white/5">
              {/* Membres actuels */}
              <div className="flex flex-col w-1/2 min-h-0">
                <div className="px-5 py-3 border-b border-gray-100 dark:border-white/5 bg-gray-50/50 dark:bg-white/[0.02]">
                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                    Membres
                    <span className="ml-2 font-normal text-gray-400 dark:text-gray-500 normal-case tracking-normal">
                      {selectedGroupe.membres.length}
                    </span>
                  </p>
                </div>
                <div className="overflow-y-auto flex-1">
                  {selectedGroupe.membres.length === 0 ? (
                    <div className="px-5 py-12 text-center">
                      <Users size={22} className="mx-auto text-gray-300 dark:text-gray-600 mb-3" />
                      <p className="text-sm text-gray-500 dark:text-gray-400">Aucun membre.</p>
                      <p className="text-xs text-gray-400 dark:text-gray-600 mt-1">Ajoutez des gestionnaires depuis le panneau de droite.</p>
                    </div>
                  ) : (
                    selectedGroupe.membres.map((m: MembreSummary) => (
                      <div key={m.id} className="flex items-center justify-between px-5 py-3 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors group">
                        <div className="flex items-center gap-3 min-w-0">
                          <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${m.is_chef ? "bg-amber-100 dark:bg-amber-400/15" : "bg-gray-100 dark:bg-white/10"}`}>
                            <span className={`text-xs font-semibold ${m.is_chef ? "text-amber-700 dark:text-amber-400" : "text-gray-600 dark:text-gray-300"}`}>{initials(m)}</span>
                          </div>
                          <div className="min-w-0">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">{displayName(m)}</p>
                              {m.is_chef && (
                                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-amber-100 dark:bg-amber-400/15 text-amber-700 dark:text-amber-400 text-xs font-medium shrink-0">
                                  <Crown size={9} />
                                  Chef
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-gray-400 dark:text-gray-500 truncate">{m.departement ?? m.email}</p>
                          </div>
                        </div>
                        <div className="opacity-0 group-hover:opacity-100 flex items-center gap-1 transition-all shrink-0">
                          <button
                            onClick={() => chefMut.mutate({ gId: selectedGroupe.id, uId: m.id, isChef: !m.is_chef })}
                            title={m.is_chef ? "Retirer le rôle de chef" : "Désigner comme chef"}
                            className={`flex items-center gap-1 px-2 py-1 rounded-lg text-xs transition-colors ${m.is_chef ? "text-amber-600 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-400/10" : "text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10"}`}
                          >
                            <Crown size={11} />
                            {m.is_chef ? "Rétrograder" : "Chef"}
                          </button>
                          <button
                            onClick={() => setConfirmRetireMembre(m)}
                            className="flex items-center gap-1 px-2 py-1 rounded-lg text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-400/10 text-xs transition-colors"
                          >
                            <UserMinus size={11} />
                            Retirer
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Ajouter des gestionnaires */}
              <div className="flex flex-col w-1/2 min-h-0">
                <div className="px-4 py-3 border-b border-gray-100 dark:border-white/5 bg-gray-50/50 dark:bg-white/[0.02]">
                  <div className="relative">
                    <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500 pointer-events-none" />
                    <input
                      type="search"
                      placeholder="Rechercher un gestionnaire…"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      className="w-full pl-8 pr-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-sm text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
                    />
                  </div>
                </div>
                <div className="overflow-y-auto flex-1">
                  {filteredCandidates.length === 0 ? (
                    <div className="px-5 py-12 text-center">
                      <UserPlus size={22} className="mx-auto text-gray-300 dark:text-gray-600 mb-3" />
                      <p className="text-sm text-gray-500 dark:text-gray-400">
                        {search ? "Aucun résultat." : "Tous les gestionnaires sont déjà membres."}
                      </p>
                    </div>
                  ) : (
                    filteredCandidates.map((u) => (
                      <div key={u.id} className="flex items-center justify-between px-5 py-3 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors group">
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="w-8 h-8 rounded-full bg-gray-100 dark:bg-white/10 flex items-center justify-center shrink-0">
                            <span className="text-xs font-semibold text-gray-600 dark:text-gray-300">{initials(u)}</span>
                          </div>
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">{displayName(u)}</p>
                            <p className="text-xs text-gray-400 dark:text-gray-500 truncate">{u.departement ?? u.email}</p>
                          </div>
                        </div>
                        <button
                          onClick={() => addMut.mutate({ gId: selectedGroupe.id, uId: u.id })}
                          className="opacity-0 group-hover:opacity-100 flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-emerald-50 dark:bg-emerald-400/10 text-emerald-700 dark:text-emerald-400 hover:bg-emerald-100 dark:hover:bg-emerald-400/20 text-xs font-medium transition-all shrink-0"
                        >
                          <UserPlus size={11} />
                          Ajouter
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center rounded-2xl border-2 border-dashed border-gray-200 dark:border-white/10" style={{ minHeight: "480px" }}>
            <div className="text-center">
              <Users size={28} className="mx-auto text-gray-300 dark:text-gray-600 mb-3" />
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Sélectionnez un groupe</p>
              <p className="text-xs text-gray-400 dark:text-gray-600 mt-1">pour gérer ses membres</p>
            </div>
          </div>
        )}
      </div>

      {confirmDeleteGroupe && (
        <ConfirmDeleteGroupe
          groupe={confirmDeleteGroupe}
          isPending={deleteMut.isPending}
          onCancel={() => setConfirmDeleteGroupe(null)}
          onConfirm={() => deleteMut.mutate(confirmDeleteGroupe.id, {
            onSuccess: () => { setSelectedGroupeId(null); setConfirmDeleteGroupe(null); },
          })}
        />
      )}

      {confirmRetireMembre && selectedGroupe && (
        <ConfirmRetireMembre
          membre={confirmRetireMembre}
          isPending={removeMut.isPending}
          onCancel={() => setConfirmRetireMembre(null)}
          onConfirm={() => removeMut.mutate({ gId: selectedGroupe.id, uId: confirmRetireMembre.id }, {
            onSuccess: () => setConfirmRetireMembre(null),
          })}
        />
      )}
    </div>
  );
}
