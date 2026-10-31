/* Linux page-walk callback actions used by the upstream xe GPU walker. */
#ifndef XG_XE_PAGEWALK_H
#define XG_XE_PAGEWALK_H
enum page_walk_action { ACTION_SUBTREE = 0, ACTION_CONTINUE = 1, ACTION_AGAIN = 2 };
#endif
