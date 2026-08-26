import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { setChefGroupe } from "../../../lib/api";
import type { Groupe, MembreSummary, UserSummary } from "../../../types/index.tsx";
import {
  fetchGroupes,
  fetchGestionnaires,
  fetchDomaines,
  createGroupe,
  deleteGroupe,
  addMembre,
  removeMembre,
} from "./api";
import { normalize, toFrenchError } from "./utils";
import GroupList from "./GroupList";
import GroupeDetailPanel, { EmptyDetailPanel } from "./GroupeDetailPanel";
import ConfirmDeleteGroupe from "./ConfirmDeleteGroupe";
import ConfirmRetireMembre from "./ConfirmRetireMembre";

export default function GroupsPage() {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["admin", "groupes"] });
    queryClient.invalidateQueries({ queryKey: ["admin", "gestionnaires"] });
    queryClient.invalidateQueries({ queryKey: ["admin", "domaines"] });
  };

  const { data: groupes = [], isLoading } = useQuery({
    queryKey: ["admin", "groupes"],
    queryFn: fetchGroupes,
  });
  const { data: gestionnaires = [] } = useQuery({
    queryKey: ["admin", "gestionnaires"],
    queryFn: fetchGestionnaires,
  });
  const { data: domaines = [] } = useQuery({
    queryKey: ["admin", "domaines"],
    queryFn: fetchDomaines,
  });

  const [createError, setCreateError] = useState<string | null>(null);
  const [memberError, setMemberError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const [pendingAddId, setPendingAddId] = useState<string | null>(null);
  const [pendingChefId, setPendingChefId] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!successMsg) return;
    const t = setTimeout(() => setSuccessMsg(null), 2500);
    return () => clearTimeout(t);
  }, [successMsg]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if ((e.key === "n" || e.key === "N") && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        setShowCreate((prev) => {
          if (prev) { setCreateError(null); setForm({ nom: "", domaine: "" }); return false; }
          setCreateError(null);
          return true;
        });
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const createMut = useMutation({
    mutationFn: createGroupe,
    onSuccess: invalidate,
    onError: (err: unknown) => setCreateError(toFrenchError(err, "add")),
  });

  const deleteMut = useMutation({
    mutationFn: deleteGroupe,
    onSuccess: invalidate,
    onError: (err: unknown) => setDeleteError(toFrenchError(err, "delete")),
  });

  const addMut = useMutation({
    mutationFn: ({ gId, uId }: { gId: string; uId: string }) => addMembre(gId, uId),
    onMutate: ({ uId }) => setPendingAddId(uId),
    onSuccess: () => { invalidate(); setSearch(""); setSuccessMsg("Membre ajouté au groupe."); },
    onError: (err: unknown) => setMemberError(toFrenchError(err, "add")),
    onSettled: () => setPendingAddId(null),
  });

  const removeMut = useMutation({
    mutationFn: ({ gId, uId }: { gId: string; uId: string }) => removeMembre(gId, uId),
    onSuccess: () => { invalidate(); setSuccessMsg("Membre retiré du groupe."); },
    onError: (err: unknown) => setRemoveError(toFrenchError(err, "remove")),
  });

  const chefMut = useMutation({
    mutationFn: ({ gId, uId, isChef }: { gId: string; uId: string; isChef: boolean }) =>
      setChefGroupe(gId, uId, isChef),
    onMutate: ({ uId }) => setPendingChefId(uId),
    onSuccess: (_, { isChef }) => { invalidate(); setSuccessMsg(isChef ? "Chef d'équipe désigné." : "Rôle de chef retiré."); },
    onError: (err: unknown) => setMemberError(toFrenchError(err, "chef")),
    onSettled: () => setPendingChefId(null),
  });

  const [selectedGroupeId, setSelectedGroupeId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ nom: "", domaine: "" });
  const [search, setSearch] = useState("");
  const [confirmDeleteGroupe, setConfirmDeleteGroupe] = useState<Groupe | null>(null);
  const [confirmRetireMembre, setConfirmRetireMembre] = useState<MembreSummary | null>(null);

  const selectedGroupe = groupes.find((g) => g.id === selectedGroupeId) ?? null;
  const removingIsLastChef = !!(
    confirmRetireMembre?.is_chef &&
    selectedGroupe?.membres.filter((m) => m.is_chef).length === 1
  );
  const memberEmails = new Set(selectedGroupe?.membres.map((m: MembreSummary) => m.email) ?? []);

  const searchTerms = normalize(search).split(/\s+/).filter(Boolean);
  const filteredCandidates = gestionnaires.filter((u) => {
    if (memberEmails.has(u.email)) return false;
    if (searchTerms.length === 0) return true;
    const haystack = normalize(`${u.prenom ?? ""} ${u.nom ?? ""} ${u.email} ${u.departement ?? ""}`);
    return searchTerms.every((term) => haystack.includes(term));
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

  function handleCancelCreate() {
    setShowCreate(false);
    setCreateError(null);
    setForm({ nom: "", domaine: "" });
  }

  function handleToggleCreate() {
    if (showCreate) {
      handleCancelCreate();
    } else {
      setShowCreate(true);
      setCreateError(null);
    }
  }

  return (
    <div className="flex flex-col h-full px-6 pt-6 pb-4 gap-4">
      {/* Page header */}
      <div className="shrink-0">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">
          Groupes &amp; gestionnaires
        </h1>
      </div>

      {/* 2-column split layout — fills remaining height */}
      <div className="flex-1 min-h-0 grid gap-4 grid-cols-1 lg:grid-cols-[280px_1fr]">
        <GroupList
          groupes={groupes}
          isLoading={isLoading}
          selectedId={selectedGroupeId}
          onSelect={(id) => {
            setSelectedGroupeId(id);
            setSearch("");
            setMemberError(null);
          }}
          showCreate={showCreate}
          onToggleCreate={handleToggleCreate}
          form={form}
          onFormChange={setForm}
          onFormSubmit={handleCreate}
          onCancelCreate={handleCancelCreate}
          isCreating={createMut.isPending}
          createError={createError}
          domaines={domaines}
        />

        {selectedGroupe ? (
          <GroupeDetailPanel
            groupe={selectedGroupe}
            candidates={filteredCandidates}
            search={search}
            onSearchChange={setSearch}
            onClose={() => {
              const btn = document.querySelector<HTMLElement>(`[data-group-id="${selectedGroupeId}"]`);
              setSelectedGroupeId(null);
              setMemberError(null);
              requestAnimationFrame(() => btn?.focus());
            }}
            onDelete={() => { setDeleteError(null); setConfirmDeleteGroupe(selectedGroupe); }}
            onAdd={(uId) => { setMemberError(null); addMut.mutate({ gId: selectedGroupe.id, uId }); }}
            onChef={(uId, isChef) => { setMemberError(null); chefMut.mutate({ gId: selectedGroupe.id, uId, isChef }); }}
            onRetirer={(membre: MembreSummary) => { setRemoveError(null); setConfirmRetireMembre(membre); }}
            pendingAddId={pendingAddId}
            pendingChefId={pendingChefId}
            memberError={memberError}
            onClearMemberError={() => setMemberError(null)}
            successMsg={successMsg}
          />
        ) : (
          <EmptyDetailPanel />
        )}
      </div>

      {/* Modals */}
      {confirmDeleteGroupe && (
        <ConfirmDeleteGroupe
          groupe={confirmDeleteGroupe}
          isPending={deleteMut.isPending}
          error={deleteError}
          onCancel={() => { setConfirmDeleteGroupe(null); setDeleteError(null); }}
          onConfirm={() =>
            deleteMut.mutate(confirmDeleteGroupe.id, {
              onSuccess: () => {
                setSelectedGroupeId(null);
                setConfirmDeleteGroupe(null);
                setDeleteError(null);
              },
            })
          }
        />
      )}

      {confirmRetireMembre && selectedGroupe && (
        <ConfirmRetireMembre
          membre={confirmRetireMembre}
          isLastChef={removingIsLastChef}
          isPending={removeMut.isPending}
          error={removeError}
          onCancel={() => { setConfirmRetireMembre(null); setRemoveError(null); }}
          onConfirm={() =>
            removeMut.mutate(
              { gId: selectedGroupe.id, uId: confirmRetireMembre.id },
              {
                onSuccess: () => { setConfirmRetireMembre(null); setRemoveError(null); },
              }
            )
          }
        />
      )}
    </div>
  );
}
