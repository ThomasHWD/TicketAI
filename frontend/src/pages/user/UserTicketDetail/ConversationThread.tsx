import { Fragment } from "react";
import { Bot, User } from "lucide-react";
import { formatDate, reponseVisible } from "./utils";
import type { TicketReponse } from "../../../types";

function UserAvatar() {
  return (
    <span className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-400 shrink-0 ring-2 ring-white dark:ring-white/10">
      <User size={16} aria-hidden="true" />
    </span>
  );
}

function BotAvatar({ pulse = false }: { pulse?: boolean }) {
  return (
    <span
      className={`inline-flex items-center justify-center w-9 h-9 rounded-full bg-emerald-500 dark:bg-emerald-600 text-white shrink-0 ring-2 ring-white dark:ring-black/40 shadow-md shadow-emerald-600/40${pulse ? " animate-pulse" : ""}`}
      aria-hidden="true"
    >
      <Bot size={16} strokeWidth={1.75} />
    </span>
  );
}

function ValidatorAvatar({ email }: { email: string | null }) {
  const initial = email ? email[0].toUpperCase() : "V";
  return (
    <span
      className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-violet-100 dark:bg-violet-500/20 text-violet-700 dark:text-violet-300 shrink-0 ring-2 ring-white dark:ring-white/10 text-sm font-semibold"
      aria-hidden="true"
    >
      {initial}
    </span>
  );
}

function QuestionBubble({
  text,
  date,
  precision = false,
}: {
  text: string;
  date: string | null;
  precision?: boolean;
}) {
  return (
    <li className="px-5 py-4 animate-in fade-in slide-in-from-bottom-1 duration-300">
      <div className="flex gap-3 items-start">
        <UserAvatar />
        <div className="flex-1 min-w-0 space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-gray-700 dark:text-gray-200">
              {precision ? "Ma précision" : "Ma question"}
            </span>
            <span className="text-xs text-gray-400 dark:text-gray-500">{formatDate(date)}</span>
          </div>
          <div className="bg-emerald-50 dark:bg-emerald-500/[0.08] border border-emerald-100 dark:border-emerald-500/20 rounded-2xl rounded-tl-sm px-4 py-3">
            <p className="text-sm text-gray-800 dark:text-gray-100 leading-relaxed whitespace-pre-wrap">
              {text}
            </p>
          </div>
        </div>
      </div>
    </li>
  );
}

function PendingAnswer({ date }: { date: string | null }) {
  return (
    <li className="px-5 py-4">
      <div className="flex gap-3 items-start">
        <BotAvatar pulse />
        <div className="flex-1 min-w-0 space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-blue-700 dark:text-blue-400">TicketAI</span>
            {date && (
              <span className="text-xs text-gray-400 dark:text-gray-500">{formatDate(date)}</span>
            )}
          </div>
          <div className="bg-blue-50/60 dark:bg-blue-500/[0.07] border border-blue-100 dark:border-blue-500/20 rounded-2xl rounded-tl-sm px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="flex gap-1 items-center" aria-label="En cours de traitement">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-400 dark:bg-blue-500 animate-pulse [animation-delay:0ms]" />
                <span className="w-1.5 h-1.5 rounded-full bg-blue-400 dark:bg-blue-500 animate-pulse [animation-delay:200ms]" />
                <span className="w-1.5 h-1.5 rounded-full bg-blue-400 dark:bg-blue-500 animate-pulse [animation-delay:400ms]" />
              </span>
              <span className="text-sm text-blue-700 dark:text-blue-300">
                Réponse en cours de traitement…
              </span>
            </div>
          </div>
        </div>
      </div>
    </li>
  );
}

function AnswerBubble({ reponse }: { reponse: TicketReponse }) {
  if (!reponseVisible(reponse)) return <PendingAnswer date={reponse.created_at} />;
  const isCanonique = reponse.canonique;
  const authorLabel = isCanonique
    ? "TicketAI"
    : reponse.validator_nom_complet ?? reponse.validator_email ?? "Validateur";
  return (
    <li className="px-5 py-4 animate-in fade-in slide-in-from-bottom-1 duration-300">
      <div className="flex gap-3 items-start">
        {isCanonique ? (
          <BotAvatar />
        ) : (
          <ValidatorAvatar email={reponse.validator_email ?? null} />
        )}
        <div className="flex-1 min-w-0 space-y-1.5">
          <div className="flex items-center gap-2">
            <span
              className={`text-xs font-semibold ${isCanonique ? "text-emerald-700 dark:text-emerald-400" : "text-violet-700 dark:text-violet-300"}`}
            >
              {authorLabel}
            </span>
            <span className="text-xs text-gray-400 dark:text-gray-500">
              {formatDate(reponse.created_at)}
            </span>
          </div>
          <div className="bg-white/90 dark:bg-white/[0.07] border border-gray-200/70 dark:border-white/10 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
            <p className="text-sm text-gray-800 dark:text-gray-100 leading-relaxed whitespace-pre-wrap">
              {reponse.contenu_corrige ?? reponse.contenu}
            </p>
          </div>
        </div>
      </div>
    </li>
  );
}

interface ConversationThreadProps {
  question: string;
  created_at: string | null;
  reponses: TicketReponse[];
}

export default function ConversationThread({ question, created_at, reponses }: ConversationThreadProps) {
  return (
    <div className="glass-card rounded-2xl overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-200 dark:border-white/10">
        <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Échange</h2>
      </div>
      <ul className="divide-y divide-gray-200 dark:divide-white/10" aria-label="Fil de la conversation">
        <QuestionBubble text={question} date={created_at} />
        {reponses.length === 0 ? (
          <PendingAnswer date={null} />
        ) : (
          reponses.map((r) => (
            <Fragment key={r.id}>
              {r.question_suivi && (
                <QuestionBubble text={r.question_suivi} date={r.created_at} precision />
              )}
              <AnswerBubble reponse={r} />
            </Fragment>
          ))
        )}
      </ul>
    </div>
  );
}
