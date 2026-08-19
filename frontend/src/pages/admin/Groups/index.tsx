import { useState } from "react";
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
import { normalize } from "./utils";
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
  const createMut = useMutation({
    mutationFn: createGroupe,
    onSuccess: invalidate,
    onError: (err: unknown) =>
      setCreateError(err instanceof Error ? err.message : "Erreur lors de la création."),
  });
  const deleteMut = useMutation({ mutationFn: deleteGroupe, onSuccess: invalidate });
  const addMut = useMutation({
    mutationFn: ({ gId, uId }: { gId: string; uId: string }) => addMembre(gId, uId),
    onSuccess: () => {
      invalidate();
      setSearch("");
    },
  });
  const removeMut = useMutation({
    mutationFn: ({ gId, uId }: { gId: string; uId: string }) => removeMembre(gId, uId),
    onSuccess: invalidate,
  });
  const chefMut = useMutation({
    mutationFn: ({ gId, uId, isChef }: { gId: string; uId: string; isChef: boolean }) =>
      setChefGroupe(gId, uId, isChef),
    onSuccess: invalidate,
  });

  const [selectedGroupeId, setSelectedGroupeId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ nom: "", domaine: "" });
  const [search, setSearch] = useState("");
  const [confirmDeleteGroupe, setConfirmDeleteGroupe] = useState<Groupe | null>(null);
  const [confirmRetireMembre, setConfirmRetireMembre] = useState<UserSummary | null>(null);

  const selectedGroupe = groupes.find((g) => g.id === selectedGroupeId) ?? null;
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
      <div
        className="flex-1 min-h-0 grid gap-4"
        style={{ gridTemplateColumns: "280px 1fr" }}
      >
        <GroupList
          groupes={groupes}
          isLoading={isLoading}
          selectedId={selectedGroupeId}
          onSelect={(id) => {
            setSelectedGroupeId(id);
            setSearch("");
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
            onClose={() => setSelectedGroupeId(null)}
            onDelete={() => setConfirmDeleteGroupe(selectedGroupe)}
            onAdd={(uId) => addMut.mutate({ gId: selectedGroupe.id, uId })}
            onChef={(uId, isChef) => chefMut.mutate({ gId: selectedGroupe.id, uId, isChef })}
            onRetirer={(membre: MembreSummary) => setConfirmRetireMembre(membre)}
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
          onCancel={() => setConfirmDeleteGroupe(null)}
          onConfirm={() =>
            deleteMut.mutate(confirmDeleteGroupe.id, {
              onSuccess: () => {
                setSelectedGroupeId(null);
                setConfirmDeleteGroupe(null);
              },
            })
          }
        />
      )}

      {confirmRetireMembre && selectedGroupe && (
        <ConfirmRetireMembre
          membre={confirmRetireMembre}
          isPending={removeMut.isPending}
          onCancel={() => setConfirmRetireMembre(null)}
          onConfirm={() =>
            removeMut.mutate(
              { gId: selectedGroupe.id, uId: confirmRetireMembre.id },
              { onSuccess: () => setConfirmRetireMembre(null) }
            )
          }
        />
      )}
    </div>
  );
}
