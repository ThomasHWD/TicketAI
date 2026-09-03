import { useState, useMemo } from "react";
import { useSearchParams, useLocation } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteDocument, listDocuments } from "../lib/api";
import { getHorsDomaine } from "../lib/api/stats";
import { useDomaines } from "../pages/backoffice/KnowledgeBase/useDomaines";
import type { Domaine, DocumentHomonyme, IndexedDocument, UpdateImpact } from "../types";
import type { PeriodeId } from "../pages/backoffice/KnowledgeBase/AnglesMorts";

export const ONGLETS = [
  { id: "documents",    label: "Documents" },
  { id: "angles-morts", label: "Angles morts" },
] as const;
export type OngletId = typeof ONGLETS[number]["id"];

export type CibleMaj =
  | { doc: IndexedDocument;  fichier?: undefined; impact?: undefined }
  | { doc: DocumentHomonyme; fichier: File;       impact?: undefined }
  | { doc: IndexedDocument;  fichier?: undefined; impact: UpdateImpact };

export function useKnowledgeBase() {
  const queryClient = useQueryClient();
  const { visibles, inscriptibles } = useDomaines();
  const location = useLocation();
  const highlightDocId = (location.state as { highlight?: string } | null)?.highlight;

  const [searchParams, setSearchParams] = useSearchParams();
  const ongletParam = searchParams.get("onglet") as OngletId | null;
  const onglet: OngletId = ongletParam === "angles-morts" ? "angles-morts" : "documents";

  const [recherche, setRecherche] = useState(searchParams.get("q") ?? "");
  const [domaine, setDomaine] = useState<Domaine | undefined>(undefined);
  const [periode, setPeriode] = useState<PeriodeId>("mois");

  function changerOnglet(id: OngletId) {
    setSearchParams(id === "documents" ? {} : { onglet: id }, { replace: true });
  }

  const [drawerOuvert, setDrawerOuvert] = useState(false);
  const [consultation, setConsultation] = useState<IndexedDocument | null>(null);
  const [historique, setHistorique] = useState<IndexedDocument | null>(null);
  const [suppression, setSuppression] = useState<IndexedDocument | null>(null);
  const [maj, setMaj] = useState<CibleMaj | null>(null);
  const [filtreEnMaj, setFiltreEnMaj] = useState(false);
  const [docSupprime, setDocSupprime] = useState<string | null>(null);

  const domainesFiltres = domaine ? [domaine] : inscriptibles;

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["documents", domaine, inscriptibles],
    queryFn: () => listDocuments(domaine, domainesFiltres.length ? domainesFiltres : undefined),
  });

  const { data: anglesData = [] } = useQuery({
    queryKey: ["angles-morts", periode],
    queryFn: () => getHorsDomaine(periode),
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
  });
  const totalAngles = anglesData.reduce((sum, e) => sum + e.nb_tickets, 0);

  const supprimer = useMutation({
    mutationFn: (doc: IndexedDocument) => deleteDocument(doc.doc_id),
    onSuccess: (_, doc) => {
      setSuppression(null);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      setDocSupprime(doc.filename ?? "Document");
      setTimeout(() => setDocSupprime(null), 4000);
    },
  });

  const termes = useMemo(
    () => recherche.trim().toLowerCase().split(/\s+/).filter(Boolean),
    [recherche],
  );

  const docs = useMemo(
    () =>
      (data?.items ?? []).filter((d) => {
        if (filtreEnMaj && d.statut !== "EN_MAJ") return false;
        if (termes.length === 0) return true;
        const foin = `${d.filename ?? ""} ${d.description ?? ""}`.toLowerCase();
        return termes.every((t) => foin.includes(t));
      }),
    [data, termes, filtreEnMaj],
  );

  const actions = useMemo(
    () => ({
      onVoir: setConsultation,
      onHistorique: setHistorique,
      onMettreAJour: (doc: IndexedDocument) => setMaj({ doc }),
      onSupprimer: setSuppression,
    }),
    [],
  );

  return {
    queryClient, visibles, inscriptibles, highlightDocId,
    onglet, changerOnglet,
    recherche, setRecherche,
    domaine, setDomaine,
    periode, setPeriode,
    drawerOuvert, setDrawerOuvert,
    consultation, setConsultation,
    historique, setHistorique,
    suppression, setSuppression,
    maj, setMaj,
    filtreEnMaj, setFiltreEnMaj,
    docSupprime,
    data, isLoading, isError, refetch,
    totalAngles,
    supprimer,
    termes, docs, actions,
    total: data?.total ?? 0,
    peutAjouter: visibles.length > 0,
    hasEnMaj: (data?.items ?? []).some((d) => d.statut === "EN_MAJ"),
  };
}
