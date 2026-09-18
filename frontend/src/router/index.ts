import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "home",
      component: () => import("../views/HomeView.vue"),
    },
    {
      path: "/projects/new",
      name: "new-project",
      component: () => import("../views/NewProjectView.vue"),
    },
    {
      path: "/projects/:projectId/board",
      name: "board",
      component: () => import("../views/BoardView.vue"),
      props: true,
    },
    {
      path: "/projects/:projectId/board/cards/:cardId",
      name: "card-detail",
      component: () => import("../views/CardDetailView.vue"),
      props: true,
    },
    {
      path: "/settings",
      name: "settings",
      component: () => import("../views/GlobalSettingsView.vue"),
    },
  ],
});

export default router;
