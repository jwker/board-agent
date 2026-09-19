/** 卡片 store：项目内卡片加载与 CRUD。 */

import { defineStore } from "pinia";
import { ref } from "vue";

import {
  createCard,
  listCards,
  updateCard,
  type Card,
  type CardCreate,
  type CardPatch,
} from "@/api/cards";

export const useCardsStore = defineStore("cards", () => {
  const cards = ref<Card[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function fetchCards(projectId: number) {
    loading.value = true;
    error.value = null;
    try {
      cards.value = await listCards(projectId);
    } catch (e) {
      error.value = e instanceof Error ? e.message : "加载卡片失败";
    } finally {
      loading.value = false;
    }
  }

  async function addCard(projectId: number, body: CardCreate): Promise<Card> {
    const card = await createCard(projectId, body);
    cards.value.unshift(card);
    return card;
  }

  async function editCard(id: number, body: CardPatch): Promise<Card> {
    const updated = await updateCard(id, body);
    const idx = cards.value.findIndex((c) => c.id === id);
    if (idx !== -1) cards.value[idx] = updated;
    return updated;
  }

  function replaceCard(card: Card) {
    const idx = cards.value.findIndex((c) => c.id === card.id);
    if (idx !== -1) cards.value[idx] = card;
  }

  /** 就地更新标题（WS card.updated 增量推送用，避免全量重拉） */
  function updateTitle(id: number, title: string) {
    const idx = cards.value.findIndex((c) => c.id === id);
    if (idx !== -1) cards.value[idx] = { ...cards.value[idx], title };
  }

  return { cards, loading, error, fetchCards, addCard, editCard, replaceCard, updateTitle };
});
