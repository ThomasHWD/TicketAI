import { Fragment } from "react";
import { ArrowRightLeft, User } from "lucide-react";
import { formatDate, BotAvatar } from "./utils";
import ReponseItem from "./ReponseItem";
import type { TicketReponse } from "../../../types";

function UserBubble({
  text,
  date,
  senderLabel,
  precision = false,
}: {
  text: string;
  date: string | null;
  senderLabel: string;
  precision?: boolean;
}) {
  return (
    <li
      className="px-5 py-4 flex justify-end animate-in fade-in slide-in-from-bottom-1 duration-200"
      aria-label={precision ? `Précision de ${senderLabel}` : `Question de ${senderLabel}`}
    >
      <div className="min-w-0 max-w-[72%] space-y-1.5">
        <div className="flex items-center justify-end gap-2">
          <span className="text-xs text-muted-foreground">{formatDate(date)}</span>
          {precision && (
            <span className="text-[10px] font-medium text-muted-foreground bg-gray-100 dark:bg-white/10 px-1.5 py-0.5 rounded-full">
              précision
            </span>
          )}
          <span className="text-xs font-semibold text-gray-700 dark:text-gray-200 truncate max-w-[120px]">
            {senderLabel}
          </span>
          <span
            className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-400 shrink-0 ring-2 ring-white dark:ring-black/20"
            aria-hidden="true"
          >
            <User size={14} />
          </span>
        </div>
        <div className="bg-emerald-50 dark:bg-emerald-500/[0.08] border border-emerald-100 dark:border-emerald-500/20 rounded-2xl rounded-tr-sm px-4 py-3 overflow-hidden">
          <p className="text-sm text-gray-800 dark:text-gray-100 leading-relaxed whitespace-pre-wrap break-words">
            {text}
          </p>
        </div>
      </div>
    </li>
  );
}

function ReroutedNote({ from }: { from: string }) {
  return (
    <li className="px-5 py-2.5 flex items-center gap-2 text-xs text-muted-foreground">
      <span className="flex-1 h-px bg-gray-100 dark:bg-white/[0.06]" aria-hidden="true" />
      <ArrowRightLeft size={11} className="shrink-0" aria-hidden="true" />
      <span>Ticket transmis depuis le service {from}</span>
      <span className="flex-1 h-px bg-gray-100 dark:bg-white/[0.06]" aria-hidden="true" />
    </li>
  );
}

function PendingBubble() {
  return (
    <li className="px-5 py-4 flex gap-3 items-start" aria-label="Réponse en cours de génération">
      <BotAvatar pulse />
      <div className="space-y-1.5">
        <span className="text-xs font-semibold text-blue-700 dark:text-blue-400">TicketAI</span>
        <div className="bg-blue-50/70 dark:bg-blue-500/[0.07] border border-blue-100 dark:border-blue-500/20 rounded-2xl rounded-tl-sm px-4 py-3">
          <div className="flex items-center gap-2.5">
            <span className="flex items-center gap-1" aria-label="En cours de génération">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-400 dark:bg-blue-500 animate-pulse [animation-delay:0ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-blue-400 dark:bg-blue-500 animate-pulse [animation-delay:200ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-blue-400 dark:bg-blue-500 animate-pulse [animation-delay:400ms]" />
            </span>
            <span className="text-sm text-blue-700 dark:text-blue-300">En cours de génération…</span>
          </div>
        </div>
      </div>
    </li>
  );
}

interface BackofficeThreadProps {
  question: string;
  created_at: string | null;
  userName: string;
  domaine: string;
  reponses: TicketReponse[];
  readOnly: boolean;
  reroute_source_domaine?: string | null;
  onChanged: () => void;
  onLockConflict: (message: string) => void;
}

export default function BackofficeThread({
  question,
  created_at,
  userName,
  domaine,
  reponses,
  readOnly,
  reroute_source_domaine,
  onChanged,
  onLockConflict,
}: BackofficeThreadProps) {
  return (
    <div className="glass-card rounded-2xl overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-100 dark:border-white/[0.06]">
        <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Conversation</h2>
      </div>
      <ul
        className="divide-y divide-gray-100 dark:divide-white/[0.04]"
        aria-label="Fil de la conversation"
        role="feed"
      >
        <UserBubble text={question} date={created_at} senderLabel={userName} />
        {reroute_source_domaine && <ReroutedNote from={reroute_source_domaine} />}
        {reponses.length === 0 ? (
          <PendingBubble />
        ) : (
          reponses.map((r) => (
            <Fragment key={r.id}>
              {r.question_suivi && (
                <UserBubble
                  text={r.question_suivi}
                  date={r.created_at}
                  senderLabel={userName}
                  precision
                />
              )}
              <ReponseItem
                reponse={r}
                domaine={domaine}
                readOnly={readOnly}
                onChanged={onChanged}
                onLockConflict={onLockConflict}
              />
            </Fragment>
          ))
        )}
      </ul>
    </div>
  );
}
