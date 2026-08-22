import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  confirmerActualite,
  confirmerActualiteLot,
  editerReponseCanonique,
  restaurerReponse,
  retirerReponse,
  supprimerReponseCanonique,
} from "../../../lib/api";

interface MutationCallbacks {
  onEditSuccess: () => void;
  onRetirerSuccess: () => void;
  onDeleteSuccess: () => void;
  onConfirmSuccess?: () => void;
  onConfirmLotSuccess?: () => void;
  onRestoreSuccess?: () => void;
}

export function useSavedAnswersMutations({
  onEditSuccess,
  onRetirerSuccess,
  onDeleteSuccess,
  onConfirmSuccess,
  onConfirmLotSuccess,
  onRestoreSuccess,
}: MutationCallbacks) {
  const queryClient = useQueryClient();

  const editMutation = useMutation({
    mutationFn: ({ id, contenu }: { id: string; contenu: string }) =>
      editerReponseCanonique(id, { contenu }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reponses-canoniques"] });
      queryClient.invalidateQueries({ queryKey: ["reponses-a-relire"] });
      onEditSuccess();
    },
  });

  const confirmMutation = useMutation({
    mutationFn: (id: string) => confirmerActualite(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reponses-a-relire"] });
      queryClient.invalidateQueries({ queryKey: ["reponses-canoniques"] });
      onConfirmSuccess?.();
    },
  });

  const confirmLotMutation = useMutation({
    mutationFn: ({ doc_id, version }: { doc_id: string; version: number }) =>
      confirmerActualiteLot(doc_id, version),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reponses-a-relire"] });
      queryClient.invalidateQueries({ queryKey: ["reponses-canoniques"] });
      onConfirmLotSuccess?.();
    },
  });

  const retirerMutation = useMutation({
    mutationFn: (id: string) => retirerReponse(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reponses-a-relire"] });
      queryClient.invalidateQueries({ queryKey: ["reponses-canoniques"] });
      queryClient.invalidateQueries({ queryKey: ["reponses-obsoletes"] });
      onRetirerSuccess();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => supprimerReponseCanonique(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reponses-canoniques"] });
      queryClient.invalidateQueries({ queryKey: ["reponses-obsoletes"] });
      onDeleteSuccess();
    },
  });

  const restoreMutation = useMutation({
    mutationFn: (id: string) => restaurerReponse(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reponses-obsoletes"] });
      queryClient.invalidateQueries({ queryKey: ["reponses-canoniques"] });
      onRestoreSuccess?.();
    },
  });

  return {
    editMutation,
    confirmMutation,
    confirmLotMutation,
    retirerMutation,
    deleteMutation,
    restoreMutation,
  };
}
