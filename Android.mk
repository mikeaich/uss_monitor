LOCAL_PATH:= $(call my-dir)

include $(CLEAR_VARS)
RED_BLACK_TREE := red_black_tree
RED_BLACK_TREE_SRC_FILES := $(RED_BLACK_TREE)/stack.c $(RED_BLACK_TREE)/red_black_tree.c $(RED_BLACK_TREE)/misc.c
LOCAL_C_INCLUDES := $(LOCAL_PATH)/$(RED_BLACK_TREE)
LOCAL_SRC_FILES := procserver.c proc_report.c $(RED_BLACK_TREE_SRC_FILES)
LOCAL_MODULE := procserver
include $(BUILD_EXECUTABLE)
