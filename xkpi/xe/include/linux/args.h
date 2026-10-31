/* LinuxKPI COUNT_ARGS stops at ten; xe RTP rules require twelve. */
#ifndef XG_XE_ARGS_H
#define XG_XE_ARGS_H
#include_next <linux/args.h>
#undef __COUNT_ARGS
#undef COUNT_ARGS
#define __COUNT_ARGS(_0,_1,_2,_3,_4,_5,_6,_7,_8,_9,_10,_11,_12,n,...) n
#define COUNT_ARGS(X...) __COUNT_ARGS(, ##X,12,11,10,9,8,7,6,5,4,3,2,1,0)
#endif
